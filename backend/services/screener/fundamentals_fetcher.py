"""Stage 2 fundamentals fetcher — 對 Stage 1 倖存者 fetch 財報 / 資產負債表 / 現金流.

設計原則：
  1. 只對 Stage 1 通過名單抓，避免對全 universe 浪費網路。
  2. 失敗回 None；下游 rule engine 把 None 視為「資料不足」。
  3. 並行抓取 + 內存 cache（一次 run 共用）。

回傳 `Fundamentals` dataclass，包含已預計算的衍生欄位（3 年 ROE 平均、FCF 正年數等），
讓 rule engine 不用再碰 pandas DataFrame。
"""

from __future__ import annotations

import logging
import math
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class Fundamentals:
    """個股財務面衍生指標（rule engine 可直接消費的精簡形式）。"""

    ticker: str
    roe_3y_avg: float | None = None  # 近 3 年平均 ROE
    revenue_cagr_3y: float | None = None  # 近 3 年營收 CAGR
    fcf_positive_years: int | None = None  # 近 3 年 FCF > 0 的年數
    eps_positive_quarters: int | None = None  # 近 4 季 EPS > 0 的季數
    debt_ratio: float | None = None  # 總負債 / 總資產
    current_ratio: float | None = None  # 流動資產 / 流動負債
    gross_margin_std_4q: float | None = None  # 近 4 季毛利率標準差（小數）
    eps_ttm: float | None = None  # TTM EPS（給 valuation 用）
    revenue_yoy_latest: float | None = None  # 最新一季營收 YoY


def _safe_get(df, label):
    """從 yfinance 的 financial DataFrame 取一列；找不到回 None list."""
    if df is None or df.empty:
        return None
    if label in df.index:
        return df.loc[label]
    return None


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _compute_fcf_positive_years(cashflow_df) -> int | None:
    """Free Cash Flow = Operating Cash Flow - Capital Expenditures.

    yfinance 在新版有 'Free Cash Flow'，舊版要自己算。回傳近 3 年正值年數。
    """
    if cashflow_df is None or cashflow_df.empty:
        return None
    fcf_row = None
    for label in ["Free Cash Flow", "FreeCashFlow"]:
        if label in cashflow_df.index:
            fcf_row = cashflow_df.loc[label]
            break
    if fcf_row is None:
        ocf = _safe_get(cashflow_df, "Operating Cash Flow")
        if ocf is None:
            ocf = _safe_get(cashflow_df, "Cash Flow From Continuing Operating Activities")
        capex = _safe_get(cashflow_df, "Capital Expenditure")
        if ocf is None or capex is None:
            return None
        fcf_row = ocf + capex  # capex 通常為負

    values = [_to_float(v) for v in fcf_row.tolist()[:3]]
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(1 for v in values if v > 0)


def _compute_roe_3y_avg(financials_df, balance_df) -> float | None:
    """近 3 年 ROE 平均 = 平均（淨利 / 年末股東權益）.

    註：分母用年末權益而非期初期末平均（yfinance 年度資料對齊成本考量），
    增資頻繁的公司 ROE 會被略為低估。
    """
    ni_row = _safe_get(financials_df, "Net Income")
    if ni_row is None:
        ni_row = _safe_get(financials_df, "Net Income Common Stockholders")
    eq_row = _safe_get(balance_df, "Stockholders Equity")
    if eq_row is None:
        eq_row = _safe_get(balance_df, "Common Stock Equity")
    if ni_row is None or eq_row is None:
        return None

    roes: list[float] = []
    ni_vals = [_to_float(v) for v in ni_row.tolist()[:3]]
    eq_vals = [_to_float(v) for v in eq_row.tolist()[:3]]
    for ni, eq in zip(ni_vals, eq_vals, strict=False):
        if ni is None or eq is None or eq <= 0:
            continue
        roes.append(ni / eq)
    if not roes:
        return None
    return statistics.mean(roes)


def _compute_revenue_cagr_3y(financials_df) -> float | None:
    rev = _safe_get(financials_df, "Total Revenue")
    if rev is None:
        return None
    vals = [_to_float(v) for v in rev.tolist()[:4]]  # 4 年才能算 3 年 CAGR
    vals = [v for v in vals if v is not None and v > 0]
    if len(vals) < 4:
        return None
    # yfinance financials 是新→舊（最新在前），所以 vals[0] 是最新
    latest, oldest = vals[0], vals[3]
    if oldest <= 0:
        return None
    try:
        return (latest / oldest) ** (1 / 3) - 1
    except (ValueError, ZeroDivisionError):
        return None


def _compute_eps_positive_quarters(quarterly_df) -> int | None:
    if quarterly_df is None or quarterly_df.empty:
        return None
    # 用 Net Income 季資料代理 EPS 正負（yfinance 季 EPS 不一定有）
    ni_row = _safe_get(quarterly_df, "Net Income")
    if ni_row is None:
        ni_row = _safe_get(quarterly_df, "Net Income Common Stockholders")
    if ni_row is None:
        return None
    vals = [_to_float(v) for v in ni_row.tolist()[:4]]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return sum(1 for v in vals if v > 0)


def _compute_debt_ratios(balance_df) -> tuple[float | None, float | None]:
    """回傳 (debt_ratio, current_ratio)."""
    if balance_df is None or balance_df.empty:
        return (None, None)

    total_assets = _safe_get(balance_df, "Total Assets")
    total_liabilities = None
    for label in [
        "Total Liabilities Net Minority Interest",
        "Total Liab",
        "Total Liabilities",
    ]:
        total_liabilities = _safe_get(balance_df, label)
        if total_liabilities is not None:
            break

    debt_ratio = None
    if total_assets is not None and total_liabilities is not None:
        ta = _to_float(total_assets.iloc[0])
        tl = _to_float(total_liabilities.iloc[0])
        if ta and tl is not None and ta > 0:
            debt_ratio = tl / ta

    current_assets = _safe_get(balance_df, "Current Assets")
    current_liab = _safe_get(balance_df, "Current Liabilities")
    current_ratio = None
    if current_assets is not None and current_liab is not None:
        ca = _to_float(current_assets.iloc[0])
        cl = _to_float(current_liab.iloc[0])
        if ca is not None and cl and cl > 0:
            current_ratio = ca / cl

    return (debt_ratio, current_ratio)


def _compute_gross_margin_std_4q(quarterly_df) -> float | None:
    if quarterly_df is None or quarterly_df.empty:
        return None
    rev = _safe_get(quarterly_df, "Total Revenue")
    gp = _safe_get(quarterly_df, "Gross Profit")
    if rev is None or gp is None:
        return None
    margins: list[float] = []
    revs = [_to_float(v) for v in rev.tolist()[:4]]
    gps = [_to_float(v) for v in gp.tolist()[:4]]
    for r, g in zip(revs, gps, strict=False):
        if r is None or g is None or r <= 0:
            continue
        margins.append(g / r)
    if len(margins) < 2:
        return None
    return statistics.pstdev(margins)


def _compute_revenue_yoy_latest(quarterly_df) -> float | None:
    rev = _safe_get(quarterly_df, "Total Revenue")
    if rev is None:
        return None
    vals = [_to_float(v) for v in rev.tolist()[:5]]  # 最新 + 4 季前 = YoY
    if len(vals) < 5 or vals[0] is None or vals[4] is None or vals[4] <= 0:
        return None
    return vals[0] / vals[4] - 1


def _fetch_one(ticker: str, eps_ttm: float | None) -> Fundamentals:
    """單檔 fetch 並計算。"""
    f = Fundamentals(ticker=ticker, eps_ttm=eps_ttm)
    # 限流退避
    for attempt in range(3):
        try:
            t = yf.Ticker(ticker)
            financials = getattr(t, "financials", None)
            balance = getattr(t, "balance_sheet", None)
            cashflow = getattr(t, "cashflow", None)
            quarterly = getattr(t, "quarterly_financials", None)

            f.roe_3y_avg = _compute_roe_3y_avg(financials, balance)
            f.revenue_cagr_3y = _compute_revenue_cagr_3y(financials)
            f.fcf_positive_years = _compute_fcf_positive_years(cashflow)
            f.eps_positive_quarters = _compute_eps_positive_quarters(quarterly)
            debt, current = _compute_debt_ratios(balance)
            f.debt_ratio = debt
            f.current_ratio = current
            f.gross_margin_std_4q = _compute_gross_margin_std_4q(quarterly)
            f.revenue_yoy_latest = _compute_revenue_yoy_latest(quarterly)
            break
        except Exception as e:
            msg = str(e).lower()
            if ("rate" in msg or "429" in msg or "too many" in msg) and attempt < 2:
                import random as _rnd
                import time as _t
                _t.sleep(1.5 * (2**attempt) + _rnd.uniform(0, 0.5))
                continue
            logger.debug("Fundamentals fetch failed for %s: %s", ticker, e)
            break
    return f


def fetch_fundamentals_bulk(
    tickers_with_eps: list[tuple[str, float | None]],
    *,
    max_workers: int = 4,
) -> dict[str, Fundamentals]:
    """並行抓取多檔的財務指標。

    Args:
        tickers_with_eps: [(ticker, eps_ttm_from_info), ...]
            EPS TTM 從 universe 階段已知的 info 帶入避免重抓。
    Returns:
        {ticker: Fundamentals}
    """
    out: dict[str, Fundamentals] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_one, t, eps): t for t, eps in tickers_with_eps}
        for fut in as_completed(futures):
            try:
                f = fut.result()
                out[f.ticker] = f
            except Exception as e:
                t = futures[fut]
                logger.warning("fetch_fundamentals failed for %s: %s", t, e)
                out[t] = Fundamentals(ticker=t)
    logger.info("Fetched fundamentals for %d tickers", len(out))
    return out
