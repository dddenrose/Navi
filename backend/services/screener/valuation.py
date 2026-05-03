"""Stage 2.5 — Rule-based fair value computation.

中長期資本利得導向的估值法：
  fair_value = TTM EPS × 產業 PE 區間（low/mid/high 取產業 PE 25/50/75 百分位）

設計選擇：
  - 用 TTM EPS（已實現），不用 forward EPS（避免分析師偏多預估）
  - 區間給三個價（low/mid/high）讓使用者自己判斷情境
  - 「合理買進區間上限」= fair_value_low × 1.05（5% 緩衝避免追高）
  - LLM 不介入此計算
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Valuation:
    method: str
    fair_value_low: float | None = None
    fair_value_mid: float | None = None
    fair_value_high: float | None = None
    buy_zone_upper: float | None = None  # 低於此價算「合理買進區間」
    implied_upside_mid_pct: float | None = None
    data_used: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class IndustryStats:
    """單一產業的估值參考值."""

    industry: str
    pe_count: int
    pe_p25: float | None = None
    pe_median: float | None = None
    pe_p75: float | None = None
    pb_median: float | None = None


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def compute_industry_stats(
    rows: list[tuple[str, float | None, float | None]],
) -> dict[str, IndustryStats]:
    """從 universe（已經是 Stage 1 倖存者）算每產業的 PE/PB 分布.

    Args:
        rows: list of (industry, pe, pb)
    Returns:
        {industry: IndustryStats}
    """
    by_ind: dict[str, list[tuple[float | None, float | None]]] = {}
    for ind, pe, pb in rows:
        by_ind.setdefault(ind, []).append((pe, pb))

    out: dict[str, IndustryStats] = {}
    for ind, items in by_ind.items():
        pes = [pe for pe, _ in items if pe is not None and 0 < pe < 100]
        pbs = [pb for _, pb in items if pb is not None and 0 < pb < 20]
        out[ind] = IndustryStats(
            industry=ind,
            pe_count=len(pes),
            pe_p25=_percentile(pes, 0.25),
            pe_median=_percentile(pes, 0.50),
            pe_p75=_percentile(pes, 0.75),
            pb_median=statistics.median(pbs) if pbs else None,
        )
    return out


def compute_valuation(
    *,
    price: float,
    eps_ttm: float | None,
    industry_stats: IndustryStats | None,
) -> Valuation:
    """規則化計算 fair value.

    若 eps_ttm 或 industry_stats 缺失 → 回 method="unavailable" 的空 Valuation。
    """
    v = Valuation(method="EPS × 產業 PE 區間")

    if eps_ttm is None or eps_ttm <= 0:
        v.method = "unavailable (EPS 缺失或為負)"
        v.notes.append("無 TTM EPS 或為負，無法用 PE 法估值")
        return v
    if industry_stats is None or industry_stats.pe_median is None:
        v.method = "unavailable (產業 PE 樣本不足)"
        v.notes.append("產業內可比股票太少，無法給出 PE 區間")
        return v

    pe_low = industry_stats.pe_p25 or industry_stats.pe_median * 0.85
    pe_mid = industry_stats.pe_median
    pe_high = industry_stats.pe_p75 or industry_stats.pe_median * 1.15

    # 樣本太少（< 5）時，強制用 median ± 15% 取代極端百分位值，避免異常區間
    if industry_stats.pe_count < 5:
        pe_low = pe_mid * 0.85
        pe_high = pe_mid * 1.15
    # 對 high 設上限：不超過 median × 1.5（避免 p75 極端值）
    pe_high = min(pe_high, pe_mid * 1.5)
    pe_low = max(pe_low, pe_mid * 0.6)

    v.fair_value_low = round(eps_ttm * pe_low, 2)
    v.fair_value_mid = round(eps_ttm * pe_mid, 2)
    v.fair_value_high = round(eps_ttm * pe_high, 2)
    v.buy_zone_upper = round(v.fair_value_low * 1.05, 2)
    if price > 0 and v.fair_value_mid:
        v.implied_upside_mid_pct = round((v.fair_value_mid / price - 1) * 100, 1)

    v.data_used = {
        "eps_ttm": round(eps_ttm, 2),
        "industry_pe_low": round(pe_low, 2),
        "industry_pe_mid": round(pe_mid, 2),
        "industry_pe_high": round(pe_high, 2),
        "industry_sample_size": industry_stats.pe_count,
    }

    if industry_stats.pe_count < 5:
        v.notes.append(f"產業樣本僅 {industry_stats.pe_count} 檔，估值區間參考性偏弱")

    return v
