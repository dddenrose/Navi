"""Screener rule engine — 規則化的篩選邏輯（Value / Momentum 兩個 profile）.

設計原則：
  1. **規則即程式碼**：每條規則是一個 RuleFn(StockData) -> RuleCheck，
     人類能讀的 `rule` / `actual` / `reference` 欄位直接用於 UI 推導過程展示。
  2. **三類規則**：must_pass（全過才資格化）/ bonus（達標數計分）/ disqualifier（任一觸發即剔除）。
  3. **資料缺失明確處理**：
       - must_pass 缺資料 = passed=False（保守）
       - bonus 缺資料 = 該項不算通過（不懲罰）
       - disqualifier 缺資料 = 不觸發（無罪推定）

Rule 定義集中在本檔最下方的 VALUE_* / MOMENTUM_* 列表，調整閾值請改這裡。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from services.screener.fundamentals_fetcher import Fundamentals

Profile = Literal["value", "momentum"]
Severity = Literal["info", "warning", "critical"]


# ── Stock data carrier ──────────────────────────────────────────────────────


@dataclass
class StockData:
    """所有 rule 需要的個股資料 — 由 factor_scorer 從 yfinance / fundamentals fetch 後組裝。"""

    ticker: str
    name: str
    industry: str
    price: float

    # Snapshot
    pe: float | None = None  # 消毒後（0 < pe <= 200），供估值/產業統計用
    pe_raw: float | None = None  # 未消毒原始值 — disqualifier 專用，避免
    # 「PE 300 被消毒成 None → 視為資料不足 → 逃過估值過熱剔除」的漏洞
    pb: float | None = None
    market_cap: float | None = None
    dividend_yield: float | None = None  # 小數，例如 0.025 = 2.5%

    # 財務面（來自 fundamentals_fetcher）
    roe_3y_avg: float | None = None
    revenue_cagr_3y: float | None = None
    fcf_positive_years: int | None = None
    eps_positive_quarters: int | None = None
    debt_ratio: float | None = None
    current_ratio: float | None = None
    gross_margin_std_4q: float | None = None
    revenue_yoy_latest: float | None = None
    eps_ttm: float | None = None

    # 月營收（TWSE OpenAPI，台股每月 10 日公布 — 比季報即時）
    revenue_monthly_yoy: float | None = None
    revenue_monthly_label: str | None = None  # 資料年月，如 "115年6月"

    # 動能 / 技術
    return_3m: float | None = None
    return_6m: float | None = None
    rel_strength_6m: float | None = None  # 相對加權指數
    sma_60: float | None = None
    sma_120: float | None = None
    volume_ratio_5_20: float | None = None
    rsi_14: float | None = None
    high_60d: float | None = None
    rsi_14_high: float | None = None  # 近 14 日 RSI 最高（背離檢查）

    # 籌碼
    foreign_net_5d: float | None = None
    foreign_net_20d: float | None = None
    foreign_consecutive_days: int | None = None

    # 產業參考（factor_scorer 計算後填入）
    # 錨優先用 TWSE 細分類（同業可比性高），樣本 < 5 檔才 fallback Navi-11 大類
    industry_pe_median: float | None = None
    industry_pb_median: float | None = None
    industry_pe_low: float | None = None
    industry_pe_high: float | None = None
    industry_size: int = 0
    industry_anchor: str | None = None  # 實際使用的估值錨（透明化）

    # 排除清單
    is_disposed: bool = False
    is_full_delivery: bool = False


# ── Rule check result ───────────────────────────────────────────────────────


@dataclass
class RuleCheck:
    """單一規則的執行結果，用於 UI 推導過程展示。"""

    rule_id: str
    name: str
    rule: str  # 人類可讀的條件，例如 "PE < 產業中位 × 1.2"
    actual: str  # 實際值，例如 "PE 22.5"
    reference: str  # 參考值/門檻，例如 "產業中位 28，門檻 33.6"
    passed: bool
    severity: Severity = "info"
    missing: bool = False  # 結構化缺資料標記 — 取代脆弱的「資料不足」字串前綴偵測


RuleFn = Callable[[StockData], RuleCheck]


@dataclass
class Rule:
    id: str
    name: str
    description: str
    fn: RuleFn


# ── Helpers ─────────────────────────────────────────────────────────────────


def _fmt(v: float | None, *, pct: bool = False, digits: int = 2) -> str:
    if v is None:
        return "資料不足"
    if pct:
        return f"{v * 100:.{digits}f}%"
    return f"{v:.{digits}f}"


def _check(rule_id: str, name: str, rule: str, actual: str, reference: str, passed: bool, *, severity: Severity = "info", missing: bool = False) -> RuleCheck:
    return RuleCheck(
        rule_id=rule_id, name=name, rule=rule, actual=actual,
        reference=reference, passed=passed, severity=severity, missing=missing,
    )


def from_fundamentals(data: StockData, fund: Fundamentals | None) -> StockData:
    """把 fundamentals_fetcher 的結果合併進 StockData."""
    if fund is None:
        return data
    data.roe_3y_avg = fund.roe_3y_avg
    data.revenue_cagr_3y = fund.revenue_cagr_3y
    data.fcf_positive_years = fund.fcf_positive_years
    data.eps_positive_quarters = fund.eps_positive_quarters
    data.debt_ratio = fund.debt_ratio
    data.current_ratio = fund.current_ratio
    data.gross_margin_std_4q = fund.gross_margin_std_4q
    data.revenue_yoy_latest = fund.revenue_yoy_latest
    data.eps_ttm = fund.eps_ttm
    return data


# ── Value strategy rules (1-3 年資本利得 / GARP) ────────────────────────────


def _v1_valuation_reasonable(d: StockData) -> RuleCheck:
    """V1 估值不貴：PE 或 PB 任一低於產業中位 × 1.2 即通過."""
    rule = "PE < 產業中位 × 1.2 或 PB < 產業中位 × 1.2"
    pe_pass = (
        d.pe is not None and d.pe > 0
        and d.industry_pe_median is not None
        and d.pe < d.industry_pe_median * 1.2
    )
    pb_pass = (
        d.pb is not None and d.pb > 0
        and d.industry_pb_median is not None
        and d.pb < d.industry_pb_median * 1.2
    )
    passed = pe_pass or pb_pass
    actual = f"PE {_fmt(d.pe)} / PB {_fmt(d.pb)}"
    ref_parts = []
    if d.industry_pe_median is not None:
        ref_parts.append(f"產業 PE 中位 {d.industry_pe_median:.1f}（門檻 {d.industry_pe_median * 1.2:.1f}）")
    if d.industry_pb_median is not None:
        ref_parts.append(f"產業 PB 中位 {d.industry_pb_median:.2f}（門檻 {d.industry_pb_median * 1.2:.2f}）")
    # 兩個分支（PE、PB）都因缺資料而無法評估時，才視為缺資料
    pe_evaluable = d.pe is not None and d.industry_pe_median is not None
    pb_evaluable = d.pb is not None and d.industry_pb_median is not None
    return _check(
        "V1", "估值不貴", rule, actual, "; ".join(ref_parts) or "產業參考缺",
        passed, missing=not (pe_evaluable or pb_evaluable),
    )


def _v2_roe(d: StockData) -> RuleCheck:
    rule = "近 3 年平均 ROE >= 12%"
    passed = d.roe_3y_avg is not None and d.roe_3y_avg >= 0.12
    return _check("V2", "獲利能力", rule, _fmt(d.roe_3y_avg, pct=True), "門檻 12%", passed, missing=d.roe_3y_avg is None)


def _v3_fcf(d: StockData) -> RuleCheck:
    rule = "近 3 年自由現金流至少 2 年為正"
    passed = d.fcf_positive_years is not None and d.fcf_positive_years >= 2
    actual = "資料不足" if d.fcf_positive_years is None else f"近 3 年 {d.fcf_positive_years} 年正值"
    return _check("V3", "現金流真實", rule, actual, "門檻 2 年", passed, missing=d.fcf_positive_years is None)


def _v4_solvency(d: StockData) -> RuleCheck:
    rule = "負債比 < 60% 且流動比 > 1.0"
    debt_ok = d.debt_ratio is not None and d.debt_ratio < 0.60
    cur_ok = d.current_ratio is not None and d.current_ratio > 1.0
    passed = debt_ok and cur_ok
    actual = f"負債比 {_fmt(d.debt_ratio, pct=True)} / 流動比 {_fmt(d.current_ratio)}"
    return _check(
        "V4", "財務安全", rule, actual, "負債比 < 60%, 流動比 > 1.0", passed,
        missing=d.debt_ratio is None or d.current_ratio is None,
    )


def _v5_eps_positive(d: StockData) -> RuleCheck:
    rule = "近 4 季 EPS 至少 3 季為正"
    passed = d.eps_positive_quarters is not None and d.eps_positive_quarters >= 3
    actual = "資料不足" if d.eps_positive_quarters is None else f"近 4 季 {d.eps_positive_quarters} 季為正"
    return _check("V5", "不在虧損循環", rule, actual, "門檻 3 季", passed, missing=d.eps_positive_quarters is None)


def _vb1_growth(d: StockData) -> RuleCheck:
    rule = "營收 3 年 CAGR >= 8%"
    passed = d.revenue_cagr_3y is not None and d.revenue_cagr_3y >= 0.08
    return _check("VB1", "成長性", rule, _fmt(d.revenue_cagr_3y, pct=True), "門檻 8%", passed, missing=d.revenue_cagr_3y is None)


def _vb2_margin_stable(d: StockData) -> RuleCheck:
    rule = "近 4 季毛利率標準差 < 2%"
    passed = d.gross_margin_std_4q is not None and d.gross_margin_std_4q < 0.02
    return _check("VB2", "毛利穩定", rule, _fmt(d.gross_margin_std_4q, pct=True), "門檻 < 2%", passed, missing=d.gross_margin_std_4q is None)


def _vb3_volume_expand(d: StockData) -> RuleCheck:
    """以量能擴增近似『法人認同』(機構資金流入訊號)."""
    rule = "5 日均量 / 20 日均量 >= 1.0"
    passed = d.volume_ratio_5_20 is not None and d.volume_ratio_5_20 >= 1.0
    return _check("VB3", "資金關注度", rule, _fmt(d.volume_ratio_5_20), "門檻 1.0", passed, missing=d.volume_ratio_5_20 is None)


def _vb4_yield(d: StockData) -> RuleCheck:
    """殖利率作為下檔保護 (你不重視現金流，但 > 2.5% 代表跌破有息接著)."""
    rule = "現金殖利率 > 2.5%"
    passed = d.dividend_yield is not None and d.dividend_yield > 0.025
    return _check("VB4", "下檔保護", rule, _fmt(d.dividend_yield, pct=True), "門檻 2.5%", passed, missing=d.dividend_yield is None)


# Value disqualifiers ───────────────────────────────────────────────────────


def _vd1_consecutive_loss(d: StockData) -> RuleCheck:
    rule = "近 4 季有 2 季以上 EPS 為負"
    triggered = d.eps_positive_quarters is not None and d.eps_positive_quarters <= 2
    return _check(
        "VD1", "排除-連續虧損", rule,
        "資料不足" if d.eps_positive_quarters is None else f"近 4 季 {d.eps_positive_quarters} 季為正",
        "門檻：>= 3 季為正",
        passed=not triggered,
        severity="critical" if triggered else "info",
        missing=d.eps_positive_quarters is None,
    )


def _vd2_disposed(d: StockData) -> RuleCheck:
    rule = "非處置股 / 非全額交割股"
    triggered = d.is_disposed or d.is_full_delivery
    return _check(
        "VD2", "排除-處置/全額交割", rule,
        "處置中" if d.is_disposed else ("全額交割" if d.is_full_delivery else "正常"),
        "TWSE 公布清單",
        passed=not triggered,
        severity="critical" if triggered else "info",
    )


def _vd4_pe_extreme(d: StockData) -> RuleCheck:
    """用未消毒的 pe_raw 判斷 — PE 300 不能因被消毒成 None 而逃過剔除."""
    rule = "PE 在合理區間（> 0 且 < 50）"
    pe = d.pe if d.pe is not None else d.pe_raw
    if pe is None:
        return _check("VD4", "排除-估值異常", rule, "資料不足", "0 < PE < 50", passed=True, missing=True)
    triggered = pe < 0 or pe > 50
    return _check(
        "VD4", "排除-估值異常", rule, _fmt(pe), "0 < PE < 50",
        passed=not triggered,
        severity="critical" if triggered else "info",
    )


# ── Momentum strategy rules (Quality + Trend, 3-12 個月) ────────────────────


def _m1_uptrend(d: StockData) -> RuleCheck:
    rule = "收盤價 > 60 日均線 > 120 日均線"
    if d.price is None or d.sma_60 is None or d.sma_120 is None:
        return _check("M1", "中期趨勢確立", rule, "資料不足", "多頭排列", passed=False, missing=True)
    passed = d.price > d.sma_60 > d.sma_120
    actual = f"價 {d.price:.2f} / SMA60 {d.sma_60:.2f} / SMA120 {d.sma_120:.2f}"
    return _check("M1", "中期趨勢確立", rule, actual, "多頭排列", passed)


def _m2_relative_strength(d: StockData) -> RuleCheck:
    rule = "6 個月相對大盤報酬 > +5%"
    passed = d.rel_strength_6m is not None and d.rel_strength_6m > 0.05
    return _check(
        "M2", "相對大盤強勢", rule,
        _fmt(d.rel_strength_6m, pct=True), "門檻 +5%", passed,
        missing=d.rel_strength_6m is None,
    )


def _m3_volume(d: StockData) -> RuleCheck:
    rule = "5 日均量 / 20 日均量 >= 1.0"
    passed = d.volume_ratio_5_20 is not None and d.volume_ratio_5_20 >= 1.0
    return _check("M3", "量能配合", rule, _fmt(d.volume_ratio_5_20), "門檻 1.0", passed, missing=d.volume_ratio_5_20 is None)


def _m4_foreign_buy(d: StockData) -> RuleCheck:
    rule = "外資近 20 日累積買超為正"
    passed = d.foreign_net_20d is not None and d.foreign_net_20d > 0
    actual = "資料不足" if d.foreign_net_20d is None else f"外資 20 日 {d.foreign_net_20d:+.0f} 張"
    return _check("M4", "籌碼面正向", rule, actual, "> 0", passed, missing=d.foreign_net_20d is None)


def _m5_quality(d: StockData) -> RuleCheck:
    rule = "近 4 季 EPS 至少 3 季為正 且 近 3 年平均 ROE > 8%"
    eps_ok = d.eps_positive_quarters is not None and d.eps_positive_quarters >= 3
    roe_ok = d.roe_3y_avg is not None and d.roe_3y_avg > 0.08
    passed = eps_ok and roe_ok
    actual = (
        f"EPS 正季數 {d.eps_positive_quarters if d.eps_positive_quarters is not None else 'N/A'}"
        f" / ROE {_fmt(d.roe_3y_avg, pct=True)}"
    )
    return _check(
        "M5", "基本面不爛", rule, actual, "EPS >=3 正 / ROE > 8%", passed,
        missing=d.eps_positive_quarters is None or d.roe_3y_avg is None,
    )


def _mb1_consecutive_buy(d: StockData) -> RuleCheck:
    rule = "外資連續買超 5 日以上"
    passed = d.foreign_consecutive_days is not None and d.foreign_consecutive_days >= 5
    return _check(
        "MB1", "法人持續買進", rule,
        "資料不足" if d.foreign_consecutive_days is None else f"連續 {d.foreign_consecutive_days} 日",
        "門檻 5 日", passed,
        missing=d.foreign_consecutive_days is None,
    )


def _mb2_revenue_yoy(d: StockData) -> RuleCheck:
    """優先用月營收 YoY（台股每月 10 日公布，最即時），缺才用季營收."""
    if d.revenue_monthly_yoy is not None:
        rule = "最新月營收 YoY > 10%"
        passed = d.revenue_monthly_yoy > 0.10
        label = f"月營收（{d.revenue_monthly_label}）" if d.revenue_monthly_label else "月營收"
        return _check(
            "MB2", "業績配合", rule,
            f"{label} {_fmt(d.revenue_monthly_yoy, pct=True)}", "門檻 10%", passed,
        )
    rule = "最近一季營收 YoY > 10%（月營收缺）"
    passed = d.revenue_yoy_latest is not None and d.revenue_yoy_latest > 0.10
    return _check("MB2", "業績配合", rule, _fmt(d.revenue_yoy_latest, pct=True), "門檻 10%", passed, missing=d.revenue_yoy_latest is None)


def _mb3_breakout(d: StockData) -> RuleCheck:
    rule = "近 60 日創新高（價格 >= 近 60 日最高 × 0.98）"
    if d.price is None or d.high_60d is None:
        return _check("MB3", "突破訊號", rule, "資料不足", "近高", passed=False, missing=True)
    passed = d.price >= d.high_60d * 0.98
    return _check(
        "MB3", "突破訊號", rule,
        f"價 {d.price:.2f} vs 60日高 {d.high_60d:.2f}",
        "近 60 日高", passed,
    )


def _mb4_rsi_healthy(d: StockData) -> RuleCheck:
    rule = "14 日 RSI 在 50-75 區間"
    if d.rsi_14 is None:
        return _check("MB4", "RSI 健康", rule, "資料不足", "50-75", passed=False, missing=True)
    passed = 50 <= d.rsi_14 <= 75
    return _check("MB4", "RSI 健康", rule, f"RSI {d.rsi_14:.1f}", "50-75（不過熱）", passed)


# Momentum disqualifiers ────────────────────────────────────────────────────


def _md1_overheated(d: StockData) -> RuleCheck:
    """用未消毒的 pe_raw 判斷 — 極端高 PE 是最需要此規則攔截的對象."""
    rule = "PE < 產業中位 × 2.0（避免過熱）"
    pe = d.pe if d.pe is not None else d.pe_raw
    if pe is None or pe <= 0 or d.industry_pe_median is None:
        # 負 PE（虧損）不屬「過熱」範疇，交由 M5 品質規則處理
        return _check("MD1", "排除-估值過熱", rule, "資料不足", "產業中位 × 2.0", passed=True, missing=True)
    threshold = d.industry_pe_median * 2.0
    triggered = pe > threshold
    return _check(
        "MD1", "排除-估值過熱", rule, f"PE {pe:.1f}",
        f"產業中位 {d.industry_pe_median:.1f} × 2.0 = {threshold:.1f}",
        passed=not triggered,
        severity="critical" if triggered else "info",
    )


def _md2_volume_price_div(d: StockData) -> RuleCheck:
    """軟警示：severity=warning 不會剔除（僅 critical 會），供使用者評估風險."""
    rule = "價格創高同時 RSI 也接近高點（無背離）"
    if d.price is None or d.high_60d is None or d.rsi_14 is None or d.rsi_14_high is None:
        return _check("MD2", "警示-量價背離", rule, "資料不足", "RSI 同步創高", passed=True, missing=True)
    making_high = d.price >= d.high_60d * 0.98
    rsi_lagging = d.rsi_14 < d.rsi_14_high - 5  # 背離認定：RSI 比近期 RSI 高點低 5 以上
    triggered = making_high and rsi_lagging
    return _check(
        "MD2", "警示-量價背離", rule,
        f"價接近高 / RSI {d.rsi_14:.1f} vs 近高 {d.rsi_14_high:.1f}",
        "若價創高但 RSI 落後 > 5 → 背離（警示，不剔除）",
        passed=not triggered,
        severity="warning" if triggered else "info",
    )


def _md3_disposed(d: StockData) -> RuleCheck:
    rule = "非處置股 / 非全額交割股"
    triggered = d.is_disposed or d.is_full_delivery
    return _check(
        "MD3", "排除-處置/全額交割", rule,
        "處置中" if d.is_disposed else ("全額交割" if d.is_full_delivery else "正常"),
        "TWSE 公布清單",
        passed=not triggered,
        severity="critical" if triggered else "info",
    )


def _md4_chip_div(d: StockData) -> RuleCheck:
    """軟警示：severity=warning 不會剔除（僅 critical 會），供使用者評估風險."""
    rule = "20 日累積買超為正但 5 日轉賣超 → 籌碼背離"
    if d.foreign_net_5d is None or d.foreign_net_20d is None:
        return _check("MD4", "警示-籌碼背離", rule, "資料不足", "5d/20d 同向", passed=True, missing=True)
    triggered = d.foreign_net_20d > 0 and d.foreign_net_5d < 0
    return _check(
        "MD4", "警示-籌碼背離", rule,
        f"5d {d.foreign_net_5d:+.0f} / 20d {d.foreign_net_20d:+.0f}",
        "5d 與 20d 應同向（警示，不剔除）",
        passed=not triggered,
        severity="warning" if triggered else "info",
    )


# ── Rule sets ──────────────────────────────────────────────────────────────


VALUE_MUST_PASS: list[Rule] = [
    Rule("V1", "估值不貴", "PE 或 PB 任一低於產業中位 × 1.2", _v1_valuation_reasonable),
    Rule("V2", "獲利能力", "近 3 年平均 ROE >= 12%", _v2_roe),
    Rule("V3", "現金流真實", "近 3 年 FCF 至少 2 年為正", _v3_fcf),
    Rule("V4", "財務安全", "負債比 < 60% 且流動比 > 1.0", _v4_solvency),
    Rule("V5", "不在虧損循環", "近 4 季 EPS 至少 3 季為正", _v5_eps_positive),
]

VALUE_BONUS: list[Rule] = [
    Rule("VB1", "成長性", "營收 3 年 CAGR >= 8%", _vb1_growth),
    Rule("VB2", "毛利穩定", "近 4 季毛利率標準差 < 2%", _vb2_margin_stable),
    Rule("VB3", "資金關注度", "5/20 日量比 >= 1.0", _vb3_volume_expand),
    Rule("VB4", "下檔保護", "現金殖利率 > 2.5%", _vb4_yield),
]

VALUE_DISQUALIFIER: list[Rule] = [
    Rule("VD1", "連續虧損", "近 4 季 EPS 為負季數 >= 2", _vd1_consecutive_loss),
    Rule("VD2", "處置股 / 全額交割", "TWSE 公布清單", _vd2_disposed),
    Rule("VD4", "估值異常", "PE < 0 或 > 50", _vd4_pe_extreme),
]

MOMENTUM_MUST_PASS: list[Rule] = [
    Rule("M1", "中期趨勢確立", "價 > SMA60 > SMA120", _m1_uptrend),
    Rule("M2", "相對大盤強勢", "6M 相對報酬 > +5%", _m2_relative_strength),
    Rule("M3", "量能配合", "5/20 日量比 >= 1.0", _m3_volume),
    Rule("M5", "基本面不爛", "EPS >= 3 季正 / ROE > 8%", _m5_quality),
]

MOMENTUM_BONUS: list[Rule] = [
    Rule("M4", "籌碼面正向", "外資 20 日累積買超 > 0", _m4_foreign_buy),
    Rule("MB1", "法人持續買進", "外資連續買超 >= 5 日", _mb1_consecutive_buy),
    Rule("MB2", "業績配合", "最新一季營收 YoY > 10%", _mb2_revenue_yoy),
    Rule("MB3", "突破訊號", "近 60 日創高", _mb3_breakout),
    Rule("MB4", "RSI 健康", "RSI 14 在 50-75", _mb4_rsi_healthy),
]

MOMENTUM_DISQUALIFIER: list[Rule] = [
    Rule("MD1", "估值過熱", "PE > 產業中位 × 2.0", _md1_overheated),
    Rule("MD2", "量價背離", "價創高但 RSI 落後（軟警示，不剔除）", _md2_volume_price_div),
    Rule("MD3", "處置股 / 全額交割", "TWSE 公布清單", _md3_disposed),
    Rule("MD4", "籌碼背離", "20d 買 5d 賣（軟警示，不剔除）", _md4_chip_div),
]


@dataclass
class RuleSet:
    profile: Profile
    must_pass: list[Rule]
    bonus: list[Rule]
    disqualifier: list[Rule]
    bonus_required: int


VALUE_RULES = RuleSet(
    profile="value",
    must_pass=VALUE_MUST_PASS,
    bonus=VALUE_BONUS,
    disqualifier=VALUE_DISQUALIFIER,
    bonus_required=2,
)

MOMENTUM_RULES = RuleSet(
    profile="momentum",
    must_pass=MOMENTUM_MUST_PASS,
    bonus=MOMENTUM_BONUS,
    disqualifier=MOMENTUM_DISQUALIFIER,
    bonus_required=2,
)


def get_rule_set(profile: Profile) -> RuleSet:
    return VALUE_RULES if profile == "value" else MOMENTUM_RULES


# ── Trace ───────────────────────────────────────────────────────────────────


@dataclass
class ScoringTrace:
    """Stage 1+2 的完整審查報告，純資料、零 LLM 介入."""

    profile: Profile
    stage1_checks: list[RuleCheck] = field(default_factory=list)
    must_pass: list[RuleCheck] = field(default_factory=list)
    bonus: list[RuleCheck] = field(default_factory=list)
    disqualifier: list[RuleCheck] = field(default_factory=list)

    must_pass_count: int = 0
    must_pass_total: int = 0
    bonus_passed: int = 0
    bonus_required: int = 0
    disqualifier_triggered: list[str] = field(default_factory=list)

    # 資料完整性
    missing_data_count: int = 0  # must_pass + bonus 內 "資料不足" 的數量
    missing_data_rule_ids: list[str] = field(default_factory=list)

    verdict: Literal["qualified", "rejected"] = "rejected"
    final_grade: Literal["Strong Pick", "Pick", "Watch", "Reject"] = "Reject"
    rejection_reason: str = ""  # 被拒原因（資料不足 / must_pass 失敗 / 觸發 disqualifier）

    def is_qualified(self) -> bool:
        return self.verdict == "qualified"


# 一檔股票最多容忍幾條 must_pass + bonus 規則處於「資料不足」狀態才能進入 qualified.
# 超過此門檻 → 強制 Reject，避免靠資料缺失躲過懲罰.
MAX_MISSING_DATA_FOR_QUALIFY = 2


def evaluate_rules(data: StockData, ruleset: RuleSet) -> ScoringTrace:
    """執行整套規則並產生 ScoringTrace（不含 Stage 1，由呼叫端附加）."""
    trace = ScoringTrace(profile=ruleset.profile)

    for r in ruleset.must_pass:
        trace.must_pass.append(r.fn(data))
    trace.must_pass_total = len(ruleset.must_pass)
    trace.must_pass_count = sum(1 for c in trace.must_pass if c.passed)

    for r in ruleset.bonus:
        trace.bonus.append(r.fn(data))
    trace.bonus_passed = sum(1 for c in trace.bonus if c.passed)
    trace.bonus_required = ruleset.bonus_required

    for r in ruleset.disqualifier:
        c = r.fn(data)
        trace.disqualifier.append(c)
        if not c.passed and c.severity == "critical":
            trace.disqualifier_triggered.append(c.rule_id)

    # 資料完整性盤點：使用結構化 missing 欄位（複合欄位規則如 V1/V4/M5
    # 的 actual 不以「資料不足」開頭，舊的字串前綴偵測會漏算）
    for c in trace.must_pass + trace.bonus:
        if c.missing:
            trace.missing_data_count += 1
            trace.missing_data_rule_ids.append(c.rule_id)

    # Verdict & grade
    must_all = trace.must_pass_count == trace.must_pass_total
    bonus_ok = trace.bonus_passed >= trace.bonus_required
    no_dq = not trace.disqualifier_triggered
    data_ok = trace.missing_data_count <= MAX_MISSING_DATA_FOR_QUALIFY

    if must_all and bonus_ok and no_dq and data_ok:
        trace.verdict = "qualified"
        trace.final_grade = "Strong Pick" if trace.bonus_passed == len(ruleset.bonus) else "Pick"
    elif must_all and no_dq and data_ok and trace.bonus_passed > 0:
        trace.verdict = "rejected"
        trace.final_grade = "Watch"
        trace.rejection_reason = f"bonus 達 {trace.bonus_passed}/{trace.bonus_required} 未達門檻"
    else:
        trace.verdict = "rejected"
        trace.final_grade = "Reject"
        if not data_ok:
            trace.rejection_reason = (
                f"資料不足規則數 {trace.missing_data_count} > {MAX_MISSING_DATA_FOR_QUALIFY}"
                f"（{','.join(trace.missing_data_rule_ids)}）"
            )
        elif trace.disqualifier_triggered:
            trace.rejection_reason = (
                f"觸發剔除條件：{','.join(trace.disqualifier_triggered)}"
            )
        elif not must_all:
            failed = [c.rule_id for c in trace.must_pass if not c.passed]
            trace.rejection_reason = f"必要規則未過：{','.join(failed)}"

    return trace
