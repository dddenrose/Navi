"""Tests for Stage 2.5 valuation."""

from __future__ import annotations

from services.screener.valuation import (
    compute_industry_stats,
    compute_valuation,
)


def test_industry_stats_computes_percentiles():
    rows = [
        ("半導體", 10, 1.0),
        ("半導體", 15, 1.5),
        ("半導體", 20, 2.0),
        ("半導體", 25, 2.5),
        ("半導體", 30, 3.0),
        ("金融", 8, 0.8),
        ("金融", 12, 1.2),
    ]
    stats = compute_industry_stats(rows)
    assert "半導體" in stats and "金融" in stats
    s = stats["半導體"]
    assert s.pe_count == 5
    assert s.pe_median == 20
    assert s.pe_p25 == 15
    assert s.pe_p75 == 25
    assert s.pb_median == 2.0


def test_industry_stats_filters_invalid_pe():
    rows = [
        ("X", -5, 1.0),  # 排除：負 PE
        ("X", 200, 1.5),  # 排除：>100
        ("X", 15, 1.5),
        ("X", 25, 2.5),
    ]
    stats = compute_industry_stats(rows)
    assert stats["X"].pe_count == 2


def test_valuation_basic_case():
    rows = [("X", pe, 1.5) for pe in [10, 15, 20, 25, 30]]
    stats = compute_industry_stats(rows)["X"]
    v = compute_valuation(price=200, eps_ttm=10, industry_stats=stats)
    assert v.fair_value_low == 150
    assert v.fair_value_mid == 200
    assert v.fair_value_high == 250
    assert v.buy_zone_upper == round(150 * 1.05, 2)
    assert v.implied_upside_mid_pct == 0


def test_valuation_unavailable_when_negative_eps():
    rows = [("X", pe, 1.5) for pe in [10, 15, 20]]
    stats = compute_industry_stats(rows)["X"]
    v = compute_valuation(price=100, eps_ttm=-2, industry_stats=stats)
    assert "unavailable" in v.method
    assert v.fair_value_mid is None


def test_valuation_unavailable_when_no_industry_data():
    v = compute_valuation(price=100, eps_ttm=5, industry_stats=None)
    assert "unavailable" in v.method


def test_valuation_small_sample_warning():
    rows = [("X", 20, 1.5), ("X", 22, 1.6), ("X", 18, 1.4)]  # 只 3 檔
    stats = compute_industry_stats(rows)["X"]
    v = compute_valuation(price=100, eps_ttm=5, industry_stats=stats)
    assert any("樣本" in n for n in v.notes)


def test_valuation_caps_extreme_high_when_small_sample():
    """樣本小且 p75 極端時，high 應被 cap 為 mid × 1.15。"""
    # p75 = 60 是 mid=20 的 3 倍，但樣本 3 檔強制改用 mid ± 15%
    rows = [("X", 5, 1.0), ("X", 20, 1.5), ("X", 60, 2.0)]
    stats = compute_industry_stats(rows)["X"]
    v = compute_valuation(price=200, eps_ttm=10, industry_stats=stats)
    # mid = 20, eps=10 → 200；high 不應 > 200 × 1.5 = 300
    assert v.fair_value_high is not None and v.fair_value_high <= 300
    assert v.fair_value_low is not None and v.fair_value_low >= 200 * 0.6


def test_valuation_caps_high_at_1_5x_when_p75_extreme():
    """足夠樣本但 p75 仍極端 → high 不超過 mid × 1.5."""
    rows = [("X", pe, 1.5) for pe in [10, 12, 15, 18, 20, 50, 60]]  # 7 檔
    stats = compute_industry_stats(rows)["X"]
    v = compute_valuation(price=100, eps_ttm=10, industry_stats=stats)
    assert v.fair_value_high is not None and v.fair_value_mid is not None
    assert v.fair_value_high <= v.fair_value_mid * 1.5 + 0.01
