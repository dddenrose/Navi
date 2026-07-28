"""產業 PE 分位數服務 — 個股本益比在同業中的相對位置（僅陳述事實，不給目標價）.

資料來源：TWSE OpenAPI BWIBBU_ALL（全市場上市股每日本益比/淨值比/殖利率）。
僅涵蓋上市（.TW）股票；上櫃（.TWO）無此 API，一律回 None。

估值錨邏輯仿 services/screener/factor_scorer.py 的兩層 fallback：
細分類（TWSE 32 類）樣本足夠優先用細分類，樣本不足才退到 Navi-11 大類；
Navi-11 的「公用其他」為異質 fallback 桶，中位數無估值意義，不作為錨。
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass

import requests

from services.screener.industry_mapper import FALLBACK_INDUSTRY, get_fine_industry, get_industry

logger = logging.getLogger(__name__)

BWIBBU_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"

# 與 services/screener/factor_scorer.py 的 MIN_FINE_PE_SAMPLE 同一門檻（獨立常數，避免耦合）
MIN_PE_SAMPLE = 5


@dataclass
class IndustryPeResult:
    ticker: str
    stock_pe: float
    industry: str  # 估值錨名稱（含細分類/大類標示）
    percentile: float  # 個股 PE 在同業中的分位數（0~100）
    sample_size: int
    median_pe: float


@dataclass
class _BwibbuStats:
    pe_by_code: dict[str, float]
    fine_pes: dict[str, list[float]]  # TWSE 細分類名稱 -> 同業 PE 清單
    coarse_pes: dict[str, list[float]]  # Navi-11 大類名稱 -> 同業 PE 清單


def _safe_pe(raw) -> float | None:
    """BWIBBU 的 PEratio 以空字串代表虧損/無 PE；同時過濾負值與極端離群值。"""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s == "-":
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    if not (0 < val < 100):
        return None
    return val


def _fetch_bwibbu_bulk(timeout: tuple[float, float] = (3, 15)) -> dict[str, float]:
    """抓全市場上市股 PE（BWIBBU_ALL）。失敗回空 dict。"""
    try:
        resp = requests.get(
            BWIBBU_URL,
            timeout=timeout,
            headers={"accept": "application/json", "User-Agent": "Navi/1.0"},
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        logger.warning("BWIBBU_ALL fetch failed: %s", e)
        return {}

    out: dict[str, float] = {}
    for row in rows:
        code = (row.get("Code") or "").strip()
        pe = _safe_pe(row.get("PEratio"))
        if code and pe is not None:
            out[code] = pe
    logger.info("BWIBBU: fetched %d valid PE values", len(out))
    return out


def _build_stats(pe_by_code: dict[str, float]) -> _BwibbuStats:
    fine_pes: dict[str, list[float]] = {}
    coarse_pes: dict[str, list[float]] = {}
    for code, pe in pe_by_code.items():
        ticker = f"{code}.TW"
        fine = get_fine_industry(ticker)
        if fine:
            fine_pes.setdefault(fine, []).append(pe)
        coarse = get_industry(ticker)
        coarse_pes.setdefault(coarse, []).append(pe)
    return _BwibbuStats(pe_by_code=pe_by_code, fine_pes=fine_pes, coarse_pes=coarse_pes)


# ── Daily TTL 快取（全市場一次抓，個股查詢從快取取）─────────────────────────

_stats_cache: _BwibbuStats | None = None
_stats_cache_time: float = 0.0
_STATS_CACHE_TTL = 86400  # 24 小時（PE 為日頻資料，daily 快取足夠）


def _get_stats_cached() -> _BwibbuStats | None:
    global _stats_cache, _stats_cache_time
    now = time.time()
    if _stats_cache is not None and (now - _stats_cache_time < _STATS_CACHE_TTL):
        return _stats_cache
    pe_by_code = _fetch_bwibbu_bulk()
    if pe_by_code:  # 失敗（空 dict）不覆蓋舊快取
        _stats_cache = _build_stats(pe_by_code)
        _stats_cache_time = now
    return _stats_cache


def _percentile_rank(values: list[float], target: float) -> float:
    """target 在 values 中的百分位（0~100）。同值計半權重，避免邊界誤導。"""
    n = len(values)
    if n == 0:
        return 50.0
    less = sum(1 for v in values if v < target)
    equal = sum(1 for v in values if v == target)
    return round((less + 0.5 * equal) / n * 100, 1)


def get_industry_pe(ticker: str) -> IndustryPeResult | None:
    """回傳個股 PE 在同產業中的分位數；資料缺失或樣本不足回 None。

    Args:
        ticker: 正規化後的股票代碼，如 '2330.TW'。僅支援上市（.TW）。
    """
    if not ticker.upper().endswith(".TW"):
        return None

    stats = _get_stats_cached()
    if stats is None:
        return None

    bare = ticker.split(".")[0]
    stock_pe = stats.pe_by_code.get(bare)
    if stock_pe is None:
        return None

    fine_name = get_fine_industry(ticker)
    coarse_name = get_industry(ticker)

    if fine_name and len(stats.fine_pes.get(fine_name, [])) >= MIN_PE_SAMPLE:
        anchor_name = f"{fine_name}（TWSE 細分類）"
        peers = stats.fine_pes[fine_name]
    elif coarse_name != FALLBACK_INDUSTRY and len(stats.coarse_pes.get(coarse_name, [])) >= MIN_PE_SAMPLE:
        anchor_name = f"{coarse_name}（Navi 大類）"
        peers = stats.coarse_pes[coarse_name]
    else:
        return None  # 樣本不足，不給分位數（避免誤導）

    percentile = _percentile_rank(peers, stock_pe)
    return IndustryPeResult(
        ticker=ticker,
        stock_pe=stock_pe,
        industry=anchor_name,
        percentile=percentile,
        sample_size=len(peers),
        median_pe=round(statistics.median(peers), 2),
    )
