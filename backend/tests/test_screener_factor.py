"""Tests for Stage 2 factor scorer (no network: synthetic StockFactors)."""

from unittest.mock import patch

import pandas as pd

from services.screener.factor_scorer import (
    PROFILE_WEIGHTS,
    ScoredStock,
    StockFactors,
    score_universe,
    top_n_per_industry,
)
from services.screener.universe import UniverseRecord


def _make_universe_record(
    ticker: str,
    industry: str,
    *,
    pe: float | None = None,
    return_3m: float | None = None,
    roe: float | None = None,
    price: float = 100.0,
) -> UniverseRecord:
    info = {}
    if pe is not None:
        info["trailingPE"] = pe
    if roe is not None:
        info["returnOnEquity"] = roe
    df = pd.DataFrame(
        {
            "Close": [price * (1 + (return_3m or 0)), price] * 60,
            "Volume": [1_000_000] * 120,
        },
        index=pd.date_range("2026-01-01", periods=120),
    )
    return UniverseRecord(
        ticker=ticker,
        name=ticker,
        industry=industry,
        price=price,
        market_cap=1e10,
        avg_turnover_20d=1e8,
        history=df,
        info=info,
    )


def test_profile_weights_sum_to_one():
    for prof, weights in PROFILE_WEIGHTS.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9, prof


@patch("services.screener.factor_scorer._benchmark_returns", return_value=(0.0, 0.0))
def test_score_universe_ranks_within_industry(_bench):
    """Two stocks in the same industry get rank 1 / 2 ordered by final_score."""
    universe = [
        _make_universe_record("AAA.TW", "半導體", pe=10, roe=0.20),  # cheap + profitable
        _make_universe_record("BBB.TW", "半導體", pe=50, roe=0.05),  # expensive
    ]
    result = score_universe(universe, profile="value", enable_chips=False)
    assert len(result) == 2
    by_ticker = {s.factors.ticker: s for s in result}
    assert by_ticker["AAA.TW"].rank_in_industry == 1
    assert by_ticker["BBB.TW"].rank_in_industry == 2
    assert by_ticker["AAA.TW"].final_score >= by_ticker["BBB.TW"].final_score


def test_top_n_per_industry_caps_per_group():
    """top_n_per_industry should cap per industry, sorted by final_score desc."""

    def _mk(ticker: str, industry: str, score: float) -> ScoredStock:
        f = StockFactors(ticker=ticker, name=ticker, industry=industry, price=100)
        return ScoredStock(factors=f, final_score=score)

    scored = [
        _mk("A.TW", "半導體", 80),
        _mk("B.TW", "半導體", 70),
        _mk("C.TW", "半導體", 90),
        _mk("D.TW", "金融保險", 60),
    ]
    out = top_n_per_industry(scored, n=2)
    by_industry = {}
    for s in out:
        by_industry.setdefault(s.factors.industry, []).append(s.factors.ticker)
    assert by_industry["半導體"] == ["C.TW", "A.TW"]
    assert by_industry["金融保險"] == ["D.TW"]
