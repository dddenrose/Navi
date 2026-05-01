"""Stage 2 — 多因子打分（規則化、產業內 z-score 標準化、Profile 權重）.

四大因子族：value / momentum / chips / quality。
每族先在「所屬產業內」做 z-score，再依 Profile 權重加總成 final_score (0-100)。

注意：MVP 階段 chips 因子（法人連續買超 / 融資融券）因 TWSE API 速率限制，
僅在 `enable_chips=True` 時抓取；預設關閉以加速 Stage 1+2 驗證。
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from typing import Literal

from services.screener.universe import UniverseRecord

logger = logging.getLogger(__name__)

Profile = Literal["value", "momentum"]

# Profile 權重（對應 proposal §2.2）
PROFILE_WEIGHTS: dict[Profile, dict[str, float]] = {
    "value": {"value": 0.50, "quality": 0.30, "chips": 0.15, "momentum": 0.05},
    "momentum": {"momentum": 0.50, "chips": 0.30, "quality": 0.15, "value": 0.05},
}


@dataclass
class StockFactors:
    """單一股票的所有原始因子數值（尚未 z-score）."""

    ticker: str
    name: str
    industry: str
    price: float

    # Snapshot（給 Stage 3 prompt 用）
    pe: float | None = None
    pb: float | None = None
    roe: float | None = None
    dividend_yield: float | None = None
    revenue_growth: float | None = None
    profit_margin: float | None = None

    # 動能因子
    return_3m: float | None = None
    return_6m: float | None = None
    rel_strength: float | None = None  # 相對大盤
    volume_expansion: float | None = None  # 5 日均量 / 20 日均量

    # Value 反向因子（PE/PB 越低越好；殖利率越高越好）
    # 後續 z-score 時 PE/PB 取負號

    # Chips（可選）
    foreign_buy_5d: float | None = None
    margin_change_5d_pct: float | None = None


@dataclass
class ScoredStock:
    factors: StockFactors
    factor_scores: dict[str, float] = field(default_factory=dict)  # 0-100 per family
    final_score: float = 0.0
    rank_in_industry: int = 0


def _safe_pct_change(series, days: int) -> float | None:
    if len(series) <= days:
        return None
    try:
        return float(series.iloc[-1] / series.iloc[-(days + 1)] - 1)
    except Exception:
        return None


def _compute_raw_factors(
    rec: UniverseRecord,
    benchmark_return_3m: float | None,
    benchmark_return_6m: float | None,
) -> StockFactors:
    info = rec.info or {}
    df = rec.history
    close = df["Close"]
    volume = df["Volume"]

    # 動能
    ret_3m = _safe_pct_change(close, 60)  # ~3 個月交易日
    ret_6m = _safe_pct_change(close, 120)

    rel_strength = None
    if ret_3m is not None and benchmark_return_3m is not None:
        rel_strength = ret_3m - benchmark_return_3m

    vol_exp = None
    if len(volume) >= 20:
        v5 = float(volume.tail(5).mean())
        v20 = float(volume.tail(20).mean())
        if v20 > 0:
            vol_exp = v5 / v20

    # 從 yf info 取基本面
    pe = info.get("trailingPE") or info.get("forwardPE")
    pb = info.get("priceToBook")
    roe = info.get("returnOnEquity")
    dy = info.get("dividendYield")
    if dy is not None and dy > 1:  # 部分版本回傳 % 形式
        dy = dy / 100
    rev_growth = info.get("revenueGrowth")
    profit_margin = info.get("profitMargins")

    return StockFactors(
        ticker=rec.ticker,
        name=rec.name,
        industry=rec.industry,
        price=rec.price,
        pe=float(pe) if pe else None,
        pb=float(pb) if pb else None,
        roe=float(roe) if roe is not None else None,
        dividend_yield=float(dy) if dy is not None else None,
        revenue_growth=float(rev_growth) if rev_growth is not None else None,
        profit_margin=float(profit_margin) if profit_margin is not None else None,
        return_3m=ret_3m,
        return_6m=ret_6m,
        rel_strength=rel_strength,
        volume_expansion=vol_exp,
    )


def _zscore(values: list[float]) -> list[float]:
    """Pop-stdev z-score；單一樣本回傳 0；NaN 過濾交給呼叫端。"""
    if len(values) < 2:
        return [0.0] * len(values)
    mu = statistics.mean(values)
    sigma = statistics.pstdev(values)
    if sigma == 0:
        return [0.0] * len(values)
    return [(v - mu) / sigma for v in values]


def _z_to_score(z: float) -> float:
    """將 z-score 映射至 0-100（粗略 sigmoid，z=0 → 50, z=±2 → ~88/12）."""
    return 100.0 / (1.0 + math.exp(-z * 1.2))


def _score_industry_group(records: list[StockFactors]) -> list[ScoredStock]:
    """對單一產業內所有股票做 z-score 並組合 family 分數."""

    def collect(attr: str, *, invert: bool = False) -> list[tuple[int, float]]:
        out = []
        for i, rec in enumerate(records):
            v = getattr(rec, attr)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            out.append((i, -v if invert else v))
        return out

    n = len(records)

    def family_score(items: list[tuple[str, bool]]) -> list[float | None]:
        """items: [(attr_name, invert)]; 對每個 attr 算產業內 z-score、再平均."""
        per_attr_scores: list[list[float | None]] = []
        for attr, invert in items:
            picks = collect(attr, invert=invert)
            if len(picks) < 2:
                per_attr_scores.append([None] * n)
                continue
            idxs, vals = zip(*picks, strict=False)
            zs = _zscore(list(vals))
            scored = [None] * n
            for idx, z in zip(idxs, zs, strict=False):
                scored[idx] = _z_to_score(z)
            per_attr_scores.append(scored)
        # 平均（忽略 None）
        result: list[float | None] = []
        for i in range(n):
            vals = [s[i] for s in per_attr_scores if s[i] is not None]
            result.append(sum(vals) / len(vals) if vals else None)
        return result

    value_scores = family_score(
        [("pe", True), ("pb", True), ("dividend_yield", False)]
    )
    momentum_scores = family_score(
        [("return_3m", False), ("return_6m", False), ("rel_strength", False), ("volume_expansion", False)]
    )
    quality_scores = family_score(
        [("roe", False), ("revenue_growth", False), ("profit_margin", False)]
    )
    # Chips 在 MVP 為 None
    chips_scores: list[float | None] = [None] * n

    out: list[ScoredStock] = []
    for i, rec in enumerate(records):
        fs = {}
        if value_scores[i] is not None:
            fs["value"] = round(value_scores[i], 1)
        if momentum_scores[i] is not None:
            fs["momentum"] = round(momentum_scores[i], 1)
        if quality_scores[i] is not None:
            fs["quality"] = round(quality_scores[i], 1)
        if chips_scores[i] is not None:
            fs["chips"] = round(chips_scores[i], 1)
        out.append(ScoredStock(factors=rec, factor_scores=fs))
    return out


def _benchmark_returns() -> tuple[float | None, float | None]:
    """加權指數 ^TWII 的 3M / 6M 報酬，作為相對強度基準."""
    try:
        import yfinance as yf

        df = yf.Ticker("^TWII").history(period="6mo")
        if df.empty:
            return (None, None)
        close = df["Close"]
        return (_safe_pct_change(close, 60), _safe_pct_change(close, 120))
    except Exception as e:
        logger.warning("benchmark fetch failed: %s", e)
        return (None, None)


def score_universe(
    universe: list[UniverseRecord],
    profile: Profile = "momentum",
) -> list[ScoredStock]:
    """主入口：計算因子 → 產業內 z-score → 加權 final score → 產業內排名."""
    bench_3m, bench_6m = _benchmark_returns()
    logger.info("Benchmark: 3M=%s, 6M=%s", bench_3m, bench_6m)

    raw = [_compute_raw_factors(r, bench_3m, bench_6m) for r in universe]

    # Group by industry
    by_industry: dict[str, list[StockFactors]] = {}
    for f in raw:
        by_industry.setdefault(f.industry, []).append(f)

    weights = PROFILE_WEIGHTS[profile]
    scored: list[ScoredStock] = []
    for industry, group in by_industry.items():
        results = _score_industry_group(group)
        # final score = weighted sum；缺項以 50（中性）填補避免懲罰過度
        for sc in results:
            total = 0.0
            for family, w in weights.items():
                v = sc.factor_scores.get(family, 50.0)
                total += w * v
            sc.final_score = round(total, 1)
        # 產業內排名
        results.sort(key=lambda x: x.final_score, reverse=True)
        for rank, sc in enumerate(results, 1):
            sc.rank_in_industry = rank
        scored.extend(results)
        logger.info(
            "Industry %s: %d stocks scored (top: %s @ %.1f)",
            industry,
            len(results),
            results[0].factors.ticker if results else "-",
            results[0].final_score if results else 0,
        )

    return scored


def top_n_per_industry(scored: list[ScoredStock], n: int = 3) -> list[ScoredStock]:
    """每產業取 Top N，方便 Stage 3 限制候選數."""
    by_industry: dict[str, list[ScoredStock]] = {}
    for s in scored:
        by_industry.setdefault(s.factors.industry, []).append(s)
    out: list[ScoredStock] = []
    for group in by_industry.values():
        group.sort(key=lambda x: x.final_score, reverse=True)
        out.extend(group[:n])
    return out
