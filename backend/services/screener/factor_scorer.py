"""Stage 2 — Rule-based screener engine（取代原本的 z-score 加權打分）。

流程：
  1. 從 UniverseRecord 計算技術 / 籌碼 / 基本面欄位 → StockData
  2. fundamentals_fetcher 並行抓財報 → 合併進 StockData
  3. 計算每產業 PE / PB 分布 → IndustryStats
  4. 執行 RuleSet（must_pass / bonus / disqualifier）→ ScoringTrace
  5. 對 qualified 的個股算 fair value → Valuation
  6. 產業內依規則排名 → industry_rank

公開入口：
  - evaluate_universe(universe, profile) -> list[EvaluatedStock]
  - top_n_per_industry(stocks, n) -> list[EvaluatedStock]
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from services.screener.fundamentals_fetcher import fetch_fundamentals_bulk
from services.screener.rules import (
    Profile,
    RuleCheck,
    ScoringTrace,
    StockData,
    evaluate_rules,
    from_fundamentals,
    get_rule_set,
)
from services.screener.universe import UniverseRecord
from services.screener.valuation import (
    Valuation,
    compute_industry_stats,
    compute_valuation,
)

logger = logging.getLogger(__name__)


# ── Output ──────────────────────────────────────────────────────────────────


@dataclass
class EvaluatedStock:
    data: StockData
    trace: ScoringTrace
    valuation: Valuation | None = None
    industry_rank: int = 0
    industry_size: int = 0  # 同產業共多少檔（顯示用）

    # Stage 1 checks（流動性 / 市值 / 排除）— 由 orchestrator 預先附加
    stage1_checks: list[RuleCheck] = field(default_factory=list)


# ── Technical indicators ────────────────────────────────────────────────────


def _safe_pct_change(series, days: int) -> float | None:
    if len(series) <= days:
        return None
    try:
        return float(series.iloc[-1] / series.iloc[-(days + 1)] - 1)
    except Exception:
        return None


def _compute_rsi(close, period: int = 14) -> tuple[float | None, float | None]:
    """Wilder's RSI；回傳 (current, max_in_last_14)."""
    if len(close) < period + 1:
        return (None, None)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - 100 / (1 + rs)
    if rsi.empty or math.isnan(rsi.iloc[-1]):
        return (None, None)
    current = float(rsi.iloc[-1])
    recent_high = float(rsi.tail(14).max()) if len(rsi) >= 14 else current
    return (current, recent_high)


def _build_stock_data(
    rec: UniverseRecord,
    *,
    benchmark_return_6m: float | None,
) -> StockData:
    info = rec.info or {}
    df = rec.history
    close = df["Close"]
    volume = df["Volume"]

    # 動能
    ret_3m = _safe_pct_change(close, 60)
    ret_6m = _safe_pct_change(close, 120)
    rel_6m = (
        ret_6m - benchmark_return_6m
        if ret_6m is not None and benchmark_return_6m is not None
        else None
    )

    # 均線
    sma_60 = float(close.tail(60).mean()) if len(close) >= 60 else None
    sma_120 = float(close.tail(120).mean()) if len(close) >= 120 else None

    # 量能
    vol_ratio = None
    if len(volume) >= 20:
        v5 = float(volume.tail(5).mean())
        v20 = float(volume.tail(20).mean())
        if v20 > 0:
            vol_ratio = v5 / v20

    # RSI / 60日高
    rsi, rsi_high = _compute_rsi(close, 14)
    high_60d = float(close.tail(60).max()) if len(close) >= 60 else None

    # info-based
    pe = info.get("trailingPE") or info.get("forwardPE")
    pb = info.get("priceToBook")
    dy = info.get("dividendYield")
    if dy is not None:
        # yfinance>=0.2.40（pyproject 鎖定）固定回傳百分比形式（0.8 表 0.8%）。
        # 勿用 `>1` 啟發式判斷格式——殖利率 <1% 的股票會被放大 100 倍。
        dy = dy / 100
    eps_ttm = info.get("trailingEps")

    # Sanity 過濾異常 PE/PB
    pe_f = float(pe) if pe and isinstance(pe, int | float) else None
    if pe_f is not None and (pe_f <= 0 or pe_f > 200):
        pe_f = None
    pb_f = float(pb) if pb and isinstance(pb, int | float) else None
    if pb_f is not None and (pb_f <= 0 or pb_f > 30):
        pb_f = None

    return StockData(
        ticker=rec.ticker,
        name=rec.name,
        industry=rec.industry,
        price=rec.price,
        pe=pe_f,
        pb=pb_f,
        market_cap=rec.market_cap,
        dividend_yield=float(dy) if dy is not None else None,
        eps_ttm=float(eps_ttm) if eps_ttm else None,
        return_3m=ret_3m,
        return_6m=ret_6m,
        rel_strength_6m=rel_6m,
        sma_60=sma_60,
        sma_120=sma_120,
        volume_ratio_5_20=vol_ratio,
        rsi_14=rsi,
        rsi_14_high=rsi_high,
        high_60d=high_60d,
    )


def _benchmark_return_6m() -> float | None:
    """加權指數 ^TWII 的 6 個月報酬."""
    try:
        import yfinance as yf

        df = yf.Ticker("^TWII").history(period="1y")
        if df.empty:
            return None
        return _safe_pct_change(df["Close"], 120)
    except Exception as e:
        logger.warning("benchmark fetch failed: %s", e)
        return None


# ── Chips integration（外資 5d / 20d / 連續日數）─────────────────────────────


def _attach_chips(data_list: list[StockData], days: int = 20) -> None:
    """從 chips_data bulk fetch 並把 5d/20d 資料填回 StockData."""
    try:
        from services.screener import chips_data
    except ImportError:
        return

    tickers = [d.ticker for d in data_list]
    try:
        # 抓 5d 用既有 helper；20d 另抓一次（同樣 endpoint 但 days 拉長）
        chips5 = chips_data.fetch_chips_bulk(tickers, days=5)
        chips20 = chips_data.fetch_chips_bulk(tickers, days=days)
    except Exception as e:
        logger.warning("Chips bulk fetch failed: %s", e)
        return

    for d in data_list:
        row5 = chips5.get(d.ticker, {})
        row20 = chips20.get(d.ticker, {})
        if "foreign_net_5d" in row5:
            d.foreign_net_5d = row5["foreign_net_5d"]
        if "foreign_consecutive_days" in row5:
            d.foreign_consecutive_days = row5["foreign_consecutive_days"]
        if "foreign_net_5d" in row20:
            # chips_data 的鍵名固定 "foreign_net_5d"，但呼叫時 days=20
            # 該值代表 20 日累積 → 對應 StockData.foreign_net_20d
            d.foreign_net_20d = row20["foreign_net_5d"]


# ── Main entry ──────────────────────────────────────────────────────────────


def evaluate_universe(
    universe: list[UniverseRecord],
    profile: Profile = "value",
    *,
    enable_chips: bool = True,
    enable_fundamentals: bool = True,
) -> list[EvaluatedStock]:
    """Stage 2 主入口 — 跑完所有規則並回傳 EvaluatedStock 清單.

    回傳 **所有** 個股（含 rejected），讓呼叫端可以決定要顯示多少給使用者。
    qualified 的會帶有 valuation；rejected 不算 valuation 以省力。
    """
    if not universe:
        return []

    bench_6m = _benchmark_return_6m()
    logger.info("Stage 2: benchmark 6M return = %s", bench_6m)

    # 1. 從 history/info 組 StockData
    data_list = [
        _build_stock_data(rec, benchmark_return_6m=bench_6m) for rec in universe
    ]

    # 2. 並行抓財務面資料（只對 Stage 1 倖存者）
    if enable_fundamentals:
        try:
            fund_map = fetch_fundamentals_bulk(
                [(d.ticker, d.eps_ttm) for d in data_list]
            )
            for d in data_list:
                from_fundamentals(d, fund_map.get(d.ticker))
        except Exception as e:
            logger.warning("Fundamentals fetch skipped: %s", e)

    # 3. 籌碼面（Momentum 必要、Value 可省）
    if enable_chips and profile == "momentum":
        _attach_chips(data_list)

    # 4. 算每產業 PE/PB 分布
    industry_stats_map = compute_industry_stats(
        [(d.industry, d.pe, d.pb) for d in data_list]
    )
    for d in data_list:
        st = industry_stats_map.get(d.industry)
        if st:
            d.industry_pe_median = st.pe_median
            d.industry_pb_median = st.pb_median
            d.industry_pe_low = st.pe_p25
            d.industry_pe_high = st.pe_p75
            d.industry_size = st.pe_count

    # 5. 跑規則
    ruleset = get_rule_set(profile)
    results: list[EvaluatedStock] = []
    for d in data_list:
        trace = evaluate_rules(d, ruleset)
        valuation: Valuation | None = None
        if trace.is_qualified():
            valuation = compute_valuation(
                price=d.price,
                eps_ttm=d.eps_ttm,
                industry_stats=industry_stats_map.get(d.industry),
            )
        results.append(
            EvaluatedStock(
                data=d, trace=trace, valuation=valuation,
                industry_size=d.industry_size,
            )
        )

    # 6. 產業內排名（只排 qualified）
    _rank_within_industry(results, profile)

    qualified = sum(1 for r in results if r.trace.is_qualified())
    logger.info(
        "Stage 2 [%s]: %d evaluated, %d qualified, %d rejected",
        profile, len(results), qualified, len(results) - qualified,
    )
    return results


def _rank_within_industry(results: list[EvaluatedStock], profile: Profile) -> None:
    by_ind: dict[str, list[EvaluatedStock]] = {}
    for r in results:
        if r.trace.is_qualified():
            by_ind.setdefault(r.data.industry, []).append(r)

    def value_key(r: EvaluatedStock):
        pe = r.data.pe if r.data.pe is not None else 1e9
        mc = r.data.market_cap or 0
        return (-r.trace.bonus_passed, pe, -mc)

    def momentum_key(r: EvaluatedStock):
        ret = r.data.return_6m if r.data.return_6m is not None else -1.0
        return (-r.trace.bonus_passed, -ret)

    key_fn = value_key if profile == "value" else momentum_key
    for group in by_ind.values():
        group.sort(key=key_fn)
        for rank, r in enumerate(group, 1):
            r.industry_rank = rank


def top_n_per_industry(
    results: list[EvaluatedStock], n: int = 3,
) -> list[EvaluatedStock]:
    """每產業取資格化的前 N 名（rejected 一律不取）."""
    by_ind: dict[str, list[EvaluatedStock]] = {}
    for r in results:
        if not r.trace.is_qualified():
            continue
        by_ind.setdefault(r.data.industry, []).append(r)
    out: list[EvaluatedStock] = []
    for group in by_ind.values():
        group.sort(key=lambda x: x.industry_rank)
        out.extend(group[:n])
    return out
