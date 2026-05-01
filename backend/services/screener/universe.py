"""Stage 1 — Universe filter（流動性 / 市值 / 排除異常股）.

純規則、零 LLM 成本。
資料來源：yfinance（一次抓 history+info），對 industry_mapper 內的 tickers 做過濾。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import yfinance as yf

from services.screener.industry_mapper import all_tickers, get_industry, get_name

logger = logging.getLogger(__name__)

# 預設門檻
MIN_AVG_TURNOVER_TWD = 50_000_000  # 20 日均成交額 > 5,000 萬
MIN_MARKET_CAP_TWD = 5_000_000_000  # 市值 > 50 億
HISTORY_PERIOD = "3mo"  # Stage 2 也需用到，這裡一次抓


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
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=HISTORY_PERIOD)
        if df.empty or len(df) < 20:
            logger.debug("Skip %s: insufficient history (%d rows)", ticker, len(df))
            return None

        # 成交額 = Close * Volume
        turnover = (df["Close"] * df["Volume"]).tail(20).mean()
        avg_turnover = float(turnover) if turnover else 0.0

        info = {}
        try:
            info = t.info or {}
        except Exception as e:
            logger.debug("info() failed for %s: %s", ticker, e)

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


def load_universe(
    tickers: list[str] | None = None,
    *,
    min_turnover: float = MIN_AVG_TURNOVER_TWD,
    min_market_cap: float = MIN_MARKET_CAP_TWD,
    max_workers: int = 8,
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
