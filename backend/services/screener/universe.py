"""Stage 1 — Universe filter（流動性 / 市值 / 排除異常股）.

純規則、零 LLM 成本。
資料來源：yfinance（一次抓 history+info），對 industry_mapper 內的 tickers 做過濾。
"""

from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests
import yfinance as yf

from services.screener.industry_mapper import all_tickers, get_industry, get_name

logger = logging.getLogger(__name__)

# 預設門檻
MIN_AVG_TURNOVER_TWD = 50_000_000  # 20 日均成交額 > 5,000 萬
MIN_MARKET_CAP_TWD = 5_000_000_000  # 市值 > 50 億
HISTORY_PERIOD = "8mo"  # 需 ≥ 6 個月以算 sma_120 / return_6m / rel_strength_6m

# yfinance 限流防護
_MAX_RETRIES = 3
_BASE_BACKOFF_SEC = 1.5


@dataclass
class UniverseRecord:
    ticker: str
    name: str
    industry: str
    price: float
    market_cap: float | None
    avg_turnover_20d: float
    history: object  # pandas.DataFrame；下游 Stage 2 沿用避免重抓
    info: dict


def _fetch_one(ticker: str) -> UniverseRecord | None:
    last_err: Exception | None = None
    df = None
    info: dict = {}
    for attempt in range(_MAX_RETRIES):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=HISTORY_PERIOD)
            try:
                info = t.info or {}
            except Exception as e:
                logger.debug("info() failed for %s: %s", ticker, e)
                info = {}
            break
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "rate" in msg or "429" in msg or "too many" in msg:
                # 指數退避 + 抖動
                delay = _BASE_BACKOFF_SEC * (2**attempt) + random.uniform(0, 0.5)
                time.sleep(delay)
                continue
            break

    if df is None:
        logger.warning("fetch_one failed for %s: %s", ticker, last_err)
        return None

    try:
        if df.empty or len(df) < 20:
            logger.debug("Skip %s: insufficient history (%d rows)", ticker, len(df))
            return None

        # 成交額 = Close * Volume
        turnover = (df["Close"] * df["Volume"]).tail(20).mean()
        avg_turnover = float(turnover) if turnover else 0.0

        market_cap = info.get("marketCap")
        price = float(df["Close"].iloc[-1])

        return UniverseRecord(
            ticker=ticker,
            name=get_name(ticker) or info.get("shortName", ""),
            industry=get_industry(ticker),
            price=price,
            market_cap=float(market_cap) if market_cap else None,
            avg_turnover_20d=avg_turnover,
            history=df,
            info=info,
        )
    except Exception as e:
        logger.warning("fetch_one failed for %s: %s", ticker, e)
        return None


def _fetch_excluded_tickers() -> set[str]:
    """擷取 TWSE 注意/處置/全額交割股代號（best-effort，失敗回空集合）。

    端點若改版可能失效；不阻塞主流程。
    """
    excluded: set[str] = set()
    endpoints = [
        # 處置股
        "https://www.twse.com.tw/announcement/punish?response=json",
        # 注意股
        "https://www.twse.com.tw/announcement/notice?response=json",
    ]
    ok_count = 0
    for url in endpoints:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code != 200:
                continue
            data = r.json()
            ok_count += 1
            rows = data.get("data") or data.get("aaData") or []
            for row in rows:
                if not row:
                    continue
                # row 各欄位順序視 endpoint 而異，掃 0~3 欄找像股號者
                for cell in row[:4]:
                    if isinstance(cell, str) and cell.isdigit() and 4 <= len(cell) <= 6:
                        excluded.add(cell)
                        break
        except Exception as e:
            logger.debug("Fetch excluded list from %s failed: %s", url, e)
    if ok_count == 0:
        # fail-open 設計（不阻塞選股），但至少要在 log 留下明確痕跡
        logger.warning(
            "TWSE 注意/處置清單全數抓取失敗 — 本期未執行異常股排除（fail-open）"
        )
    return excluded


def load_universe(
    tickers: list[str] | None = None,
    *,
    min_turnover: float = MIN_AVG_TURNOVER_TWD,
    min_market_cap: float = MIN_MARKET_CAP_TWD,
    max_workers: int = 4,
) -> list[UniverseRecord]:
    """並行載入 universe 並做 Stage 1 過濾.

    Args:
        tickers: 自訂股票池；None 則使用 industry_mapper 全部 tickers。
        min_turnover: 20 日均成交額門檻（TWD）。
        min_market_cap: 市值門檻（TWD），None 或 0 表示不過濾。
        max_workers: 並行 worker 數。
    """
    candidates = tickers or all_tickers()
    logger.info("Stage 1: loading %d candidates", len(candidates))

    records: list[UniverseRecord] = []
    excluded = _fetch_excluded_tickers()
    if excluded:
        candidates = [t for t in candidates if t.split(".")[0] not in excluded]
        logger.info("Excluded %d disposed/full-delivery tickers", len(excluded))

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_one, t): t for t in candidates}
        for fut in as_completed(futures):
            rec = fut.result()
            if rec is None:
                continue
            # 流動性
            if rec.avg_turnover_20d < min_turnover:
                continue
            # 市值（部分股可能拿不到 marketCap，給予寬鬆放行）
            if (
                min_market_cap
                and rec.market_cap is not None
                and rec.market_cap < min_market_cap
            ):
                continue
            records.append(rec)

    logger.info(
        "Stage 1: %d → %d passed (min_turnover=%.0f, min_mcap=%.0f)",
        len(candidates),
        len(records),
        min_turnover,
        min_market_cap or 0,
    )
    return records
