"""Tests for screener rule engine — focus on rule logic correctness."""

from __future__ import annotations

import pytest

from services.screener.rules import (
    StockData,
    evaluate_rules,
    get_rule_set,
)


def _value_stock_strong() -> StockData:
    """完美的價值型公司：所有 must_pass 全過、所有 bonus 全過、無 disqualifier。"""
    return StockData(
        ticker="9999.TW",
        name="Test",
        industry="X",
        price=100,
        pe=18,  # 產業中位 25 × 1.2 = 30，遠低於
        pb=1.5,
        market_cap=10_000_000_000,
        dividend_yield=0.045,
        roe_3y_avg=0.18,
        revenue_cagr_3y=0.10,
        fcf_positive_years=3,
        eps_positive_quarters=4,
        debt_ratio=0.30,
        current_ratio=2.0,
        gross_margin_std_4q=0.01,
        revenue_yoy_latest=0.05,
        eps_ttm=8.0,
        volume_ratio_5_20=1.2,
        industry_pe_median=25,
        industry_pb_median=2.5,
        industry_size=10,
    )


def _momentum_stock_strong() -> StockData:
    return StockData(
        ticker="8888.TW",
        name="MoTest",
        industry="X",
        price=120,
        sma_60=110,
        sma_120=100,
        return_6m=0.20,
        rel_strength_6m=0.15,
        volume_ratio_5_20=1.4,
        foreign_net_20d=500_000_000,
        foreign_consecutive_days=5,
        eps_positive_quarters=4,
        roe_3y_avg=0.12,
        rsi_14=65,
        high_60d=120,
        revenue_yoy_latest=0.10,
        industry_size=10,
    )


# ── Value profile ───────────────────────────────────────────────────────────


def test_value_strong_pick_is_qualified_strong():
    rs = get_rule_set("value")
    trace = evaluate_rules(_value_stock_strong(), rs)
    assert trace.is_qualified()
    assert trace.must_pass_count == trace.must_pass_total
    assert trace.final_grade == "Strong Pick"
    assert not trace.disqualifier_triggered


def test_value_high_pe_fails_must_pass():
    s = _value_stock_strong()
    s.pe = 50  # 高於產業中位 × 1.2
    s.pb = 5  # 同樣高
    trace = evaluate_rules(s, get_rule_set("value"))
    assert not trace.is_qualified()
    v1 = next(c for c in trace.must_pass if c.rule_id == "V1")
    assert not v1.passed


def test_value_low_roe_fails():
    s = _value_stock_strong()
    s.roe_3y_avg = 0.05
    trace = evaluate_rules(s, get_rule_set("value"))
    assert not trace.is_qualified()


def test_value_disposed_stock_disqualified():
    s = _value_stock_strong()
    s.is_disposed = True
    trace = evaluate_rules(s, get_rule_set("value"))
    assert trace.disqualifier_triggered
    assert not trace.is_qualified()


# ── Momentum profile ────────────────────────────────────────────────────────


def test_momentum_strong_pick_qualified():
    rs = get_rule_set("momentum")
    trace = evaluate_rules(_momentum_stock_strong(), rs)
    assert trace.is_qualified()
    assert trace.must_pass_count == trace.must_pass_total


def test_momentum_below_sma60_fails():
    s = _momentum_stock_strong()
    s.price = 90  # 低於 sma_60=110
    trace = evaluate_rules(s, get_rule_set("momentum"))
    assert not trace.is_qualified()
    m1 = next(c for c in trace.must_pass if c.rule_id == "M1")
    assert not m1.passed


def test_momentum_weak_relative_strength_fails():
    s = _momentum_stock_strong()
    s.rel_strength_6m = -0.10
    trace = evaluate_rules(s, get_rule_set("momentum"))
    assert not trace.is_qualified()


# ── Missing data behavior ───────────────────────────────────────────────────


def test_missing_must_pass_data_fails_safely():
    s = StockData(ticker="X", name="X", industry="X", price=100, industry_pe_median=25)
    # 完全沒填財務 / 動能資料
    trace = evaluate_rules(s, get_rule_set("value"))
    assert not trace.is_qualified()
    # disqualifier 不應誤觸發 (無罪推定)
    assert not trace.disqualifier_triggered


def test_too_many_missing_data_forces_reject_even_if_must_pass_count_high():
    """避免「靠資料缺失躲過懲罰」：missing > MAX_MISSING_DATA_FOR_QUALIFY → 強制 Reject."""
    # 一檔股票 must_pass 都因「資料不足」回傳 False、bonus 也大量資料不足
    s = StockData(ticker="X", name="X", industry="X", price=100)
    trace = evaluate_rules(s, get_rule_set("value"))
    assert trace.final_grade == "Reject"
    assert trace.missing_data_count >= 3
    assert "資料不足" in trace.rejection_reason


def test_data_completeness_blocks_qualify_when_partial_missing():
    """即使所有 must_pass 都是真的過了，但 bonus 太多資料不足 → 不該被 reward 升 Pick."""
    s = _value_stock_strong()
    # 把 bonus 用得到的數據全部清掉 → bonus 應全部「資料不足」
    s.revenue_cagr_3y = None
    s.gross_margin_std_4q = None
    s.volume_ratio_5_20 = None
    s.dividend_yield = None
    trace = evaluate_rules(s, get_rule_set("value"))
    # 4 個 bonus 全資料不足，超過門檻 → Reject
    assert trace.missing_data_count >= 3
    assert trace.final_grade == "Reject"
    assert trace.verdict == "rejected"


def test_rejection_reason_populated():
    s = _value_stock_strong()
    s.is_disposed = True  # 觸發 VD2
    trace = evaluate_rules(s, get_rule_set("value"))
    assert trace.disqualifier_triggered
    assert "剔除條件" in trace.rejection_reason


@pytest.mark.parametrize("profile", ["value", "momentum"])
def test_get_rule_set_returns_correct_profile(profile):
    rs = get_rule_set(profile)
    assert rs.profile == profile
    assert rs.must_pass and rs.bonus and rs.disqualifier
