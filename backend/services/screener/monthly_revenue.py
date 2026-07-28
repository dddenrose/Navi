"""TWSE OpenAPI 月營收 fetcher — 上市公司每月營業收入彙總表（t187ap05_L）.

台股每月 10 日前公布上月營收，是基本面最即時的公開訊號；
yfinance 只有季營收（且常缺前 5 季無法算 YoY），此模組補上這個缺口。

一次呼叫回傳全市場（~1000 檔），成本極低；資料約落後 1-2 個月內，
label 欄位保留資料年月供前端與 AI 揭露時效。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

MONTHLY_REVENUE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"


@dataclass
class MonthlyRevenue:
    code: str  # 純代號，如 "2330"
    yoy: float | None  # 去年同月增減，小數（0.30 = +30%）
    label: str  # 資料年月，如 "115年5月"
    revenue: int | None = None  # 當月營收（仟元）
    mom: float | None = None  # 上月比較增減，小數
    yoy_acc: float | None = None  # 累計營收較去年同期增減，小數


def _parse_yoy(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw) / 100
    except (TypeError, ValueError):
        return None


def _parse_revenue(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _format_label(roc_ym: str) -> str:
    """'11505' → '115年5月'；格式異常時原樣回傳。"""
    if len(roc_ym) >= 5 and roc_ym.isdigit():
        return f"{roc_ym[:-2]}年{int(roc_ym[-2:])}月"
    return roc_ym


def fetch_monthly_revenue_bulk(
    timeout: tuple[float, float] = (3, 15),
) -> dict[str, MonthlyRevenue]:
    """抓全市場最新一期月營收 YoY。失敗回空 dict（呼叫端視為資料缺失）。

    Returns:
        {bare_code: MonthlyRevenue}
    """
    try:
        resp = requests.get(
            MONTHLY_REVENUE_URL,
            timeout=timeout,
            headers={"accept": "application/json", "User-Agent": "Navi/1.0"},
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        logger.warning("Monthly revenue fetch failed: %s", e)
        return {}

    out: dict[str, MonthlyRevenue] = {}
    for row in rows:
        code = (row.get("公司代號") or "").strip()
        if not code:
            continue
        out[code] = MonthlyRevenue(
            code=code,
            yoy=_parse_yoy(row.get("營業收入-去年同月增減(%)")),
            label=_format_label((row.get("資料年月") or "").strip()),
            revenue=_parse_revenue(row.get("營業收入-當月營收")),
            mom=_parse_yoy(row.get("營業收入-上月比較增減(%)")),
            yoy_acc=_parse_yoy(row.get("累計營業收入-前期比較增減(%)")),
        )
    logger.info("Monthly revenue: fetched %d companies", len(out))
    return out


# ── 個股查詢用：全市場資料的 daily TTL 快取 ───────────────────────────────────
# screener 既有的 _attach_monthly_revenue 仍呼叫上面未快取的 fetch_monthly_revenue_bulk()，
# 行為不變；以下是額外提供給個股頁「單檔查詢」使用的快取層。

_bulk_cache: dict[str, MonthlyRevenue] | None = None
_bulk_cache_time: float = 0.0
_BULK_CACHE_TTL = 86400  # 24 小時（月營收為月頻資料，daily 快取足夠）


def fetch_monthly_revenue_bulk_cached() -> dict[str, MonthlyRevenue]:
    """`fetch_monthly_revenue_bulk()` 的 daily TTL 快取版本，供個股單檔查詢用。"""
    global _bulk_cache, _bulk_cache_time
    now = time.time()
    if _bulk_cache is not None and (now - _bulk_cache_time < _BULK_CACHE_TTL):
        return _bulk_cache
    data = fetch_monthly_revenue_bulk()
    if data:  # 失敗（空 dict）不覆蓋舊快取
        _bulk_cache = data
        _bulk_cache_time = now
    return _bulk_cache or {}


def get_monthly_revenue(ticker: str) -> MonthlyRevenue | None:
    """單檔月營收查詢（僅上市 .TW；OTC 無此 API，回 None）。

    Args:
        ticker: 可含 .TW/.TWO 後綴的股票代碼。
    """
    if not ticker.upper().endswith(".TW"):
        return None
    bare = ticker.split(".")[0]
    data = fetch_monthly_revenue_bulk_cached()
    return data.get(bare)
