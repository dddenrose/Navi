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

# 細分類 PE 樣本至少要幾檔才用細分類當估值錨（否則 fallback Navi-11 大類）
MIN_FINE_PE_SAMPLE = 5


# ── Output ──────────────────────────────────────────────────────────────────


@dataclass
class EvaluatedStock:
    data: StockData
    trace: ScoringTrace
    valuation: Valuation | None = None
    industry_rank: int = 0
    industry_size: int = 0  # 本期評估的同產業檔數（顯示用）
    rank_overall: int = 0  # 全市場排名（select_top_picks 填入；0 = 未入選）

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
    # 只用 trailingPE —— 不 fallback forwardPE：兩者口徑不同，混用會污染
    # 產業中位數統計與估值錨（部分股用歷史盈餘、部分用分析師預估）。
    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    dy = info.get("dividendYield")
    if dy is not None:
        # yfinance>=0.2.40 起固定回傳百分比形式（0.8 表 0.8%）。
        # 勿用 `>1` 啟發式判斷格式——殖利率 <1% 的股票會被放大 100 倍。
        dy = dy / 100
        # Runtime sanity：pyproject 只鎖版本下限，若 yfinance 未來改回小數
        # 形式，除以 100 會讓殖利率縮小 100 倍（難察覺）；反向改動則會
        # 出現 >15% 的異常值（台股正常範圍極少超過）。兩側都防：
        if dy > 0.15:
            logger.warning(
                "Suspicious dividend_yield %.4f for %s — treating as missing "
                "(yfinance semantics may have changed)", dy, rec.ticker,
            )
            dy = None
    eps_ttm = info.get("trailingEps")

    # Sanity 過濾異常 PE/PB；原始 PE 另存 pe_raw 供 disqualifier 使用
    # （否則 PE 300 會被洗成「資料不足」而逃過 MD1/VD4 剔除）
    pe_raw = float(pe) if pe is not None and isinstance(pe, int | float) else None
    pe_f = pe_raw
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
        pe_raw=pe_raw,
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
    """從 chips_data bulk fetch（單次、多視窗）把 5d/20d 資料填回 StockData."""
    try:
        from services.screener import chips_data
    except ImportError:
        return

    tickers = [d.ticker for d in data_list]
    try:
        chips = chips_data.fetch_chips_bulk(tickers, windows=(5, days))
    except Exception as e:
        logger.warning("Chips bulk fetch failed: %s", e)
        return

    for d in data_list:
        row = chips.get(d.ticker, {})
        if "foreign_net_5d" in row:
            d.foreign_net_5d = row["foreign_net_5d"]
        if "foreign_consecutive_days" in row:
            d.foreign_consecutive_days = row["foreign_consecutive_days"]
        if f"foreign_net_{days}d" in row:
            d.foreign_net_20d = row[f"foreign_net_{days}d"]


def _attach_monthly_revenue(data_list: list[StockData]) -> None:
    """把 TWSE 月營收 YoY 填回 StockData（MB2 優先消費，缺才 fallback 季營收）."""
    try:
        from services.screener.monthly_revenue import fetch_monthly_revenue_bulk

        rev_map = fetch_monthly_revenue_bulk()
    except Exception as e:
        logger.warning("Monthly revenue attach skipped: %s", e)
        return
    if not rev_map:
        return
    for d in data_list:
        bare = d.ticker.split(".")[0]
        rec = rev_map.get(bare)
        if rec and rec.yoy is not None:
            d.revenue_monthly_yoy = rec.yoy
            d.revenue_monthly_label = rec.label


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

    # 3.5 月營收 YoY（TWSE OpenAPI，一次呼叫全市場；失敗不阻塞）
    if enable_fundamentals:
        _attach_monthly_revenue(data_list)

    # 4. 算產業 PE/PB 分布 — 兩層錨：
    #    TWSE 細分類（32 類，同業可比性高）優先；
    #    細分類 PE 樣本 < MIN_FINE_PE_SAMPLE 檔時 fallback Navi-11 大類。
    #    「公用其他」大類是異質 fallback 桶，其中位數無估值意義 → 不做估值。
    from services.screener.industry_mapper import get_fine_industry

    fine_stats_map = compute_industry_stats(
        [(get_fine_industry(d.ticker) or d.industry, d.pe, d.pb) for d in data_list]
    )
    coarse_stats_map = compute_industry_stats(
        [(d.industry, d.pe, d.pb) for d in data_list]
    )
    # 顯示用產業規模 = 本期評估的同業檔數（舊版用「有 PE 的檔數」，
    # 與排名分母語意不一致）
    evaluated_per_industry: dict[str, int] = {}
    for d in data_list:
        evaluated_per_industry[d.industry] = evaluated_per_industry.get(d.industry, 0) + 1

    anchor_stats: dict[str, "IndustryStats | None"] = {}
    for d in data_list:
        fine_name = get_fine_industry(d.ticker)
        fine_st = fine_stats_map.get(fine_name) if fine_name else None
        coarse_st = coarse_stats_map.get(d.industry)
        if fine_st and fine_st.pe_count >= MIN_FINE_PE_SAMPLE:
            st, anchor = fine_st, f"{fine_name}（TWSE 細分類）"
        else:
            st, anchor = coarse_st, f"{d.industry}（Navi 大類）"
        anchor_stats[d.ticker] = st
        if st:
            d.industry_pe_median = st.pe_median
            d.industry_pb_median = st.pb_median
            d.industry_pe_low = st.pe_p25
            d.industry_pe_high = st.pe_p75
            d.industry_anchor = anchor
        d.industry_size = evaluated_per_industry.get(d.industry, 0)

    # 5. 跑規則
    ruleset = get_rule_set(profile)
    results: list[EvaluatedStock] = []
    for d in data_list:
        trace = evaluate_rules(d, ruleset)
        valuation: Valuation | None = None
        if trace.is_qualified():
            if d.industry == "公用其他" and (
                d.industry_anchor or ""
            ).startswith("公用其他"):
                valuation = Valuation(
                    method="unavailable (異質產業桶)",
                    notes=[
                        "「公用其他」為混合 fallback 分類，同業 PE 中位數"
                        "無可比性，不提供估值區間"
                    ],
                )
            else:
                valuation = compute_valuation(
                    price=d.price,
                    eps_ttm=d.eps_ttm,
                    industry_stats=anchor_stats.get(d.ticker),
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
    """每產業取資格化的前 N 名（rejected 一律不取）.

    Deprecated：產業配額會讓弱勢產業也保送 N 檔，選不出「全市場最棒」。
    線上管線已改用 select_top_picks；此函式保留給比較實驗用。
    """
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


def select_top_picks(
    results: list[EvaluatedStock],
    profile: Profile,
    *,
    total: int = 10,
    max_per_industry: int = 2,
) -> list[EvaluatedStock]:
    """全市場排名 + 單一產業上限 — 取代每產業 top-N 的產業配額制.

    排序鍵（與產業內排名一致的邏輯，跨產業可比版本）：
      - momentum：bonus 通過數 → 6 個月相對大盤強度
      - value：bonus 通過數 → PE 相對產業中位的折價（跨產業用相對值，
        避免拿半導體的 PE 跟鋼鐵的 PE 直接比）→ 市值大者優先

    回傳依全市場排名排序；同時把 rank_overall 寫回 EvaluatedStock。
    """
    qualified = [r for r in results if r.trace.is_qualified()]

    def momentum_key(r: EvaluatedStock):
        strength = (
            r.data.rel_strength_6m
            if r.data.rel_strength_6m is not None
            else (r.data.return_6m if r.data.return_6m is not None else -9.0)
        )
        return (-r.trace.bonus_passed, -strength)

    def value_key(r: EvaluatedStock):
        if r.data.pe is not None and r.data.industry_pe_median:
            pe_rel = r.data.pe / r.data.industry_pe_median
        else:
            pe_rel = float("inf")
        return (-r.trace.bonus_passed, pe_rel, -(r.data.market_cap or 0))

    qualified.sort(key=value_key if profile == "value" else momentum_key)

    selected: list[EvaluatedStock] = []
    per_ind: dict[str, int] = {}
    for r in qualified:
        ind = r.data.industry
        if per_ind.get(ind, 0) >= max_per_industry:
            continue
        selected.append(r)
        per_ind[ind] = per_ind.get(ind, 0) + 1
        if len(selected) >= total:
            break

    for rank, r in enumerate(selected, 1):
        r.rank_overall = rank
    return selected
