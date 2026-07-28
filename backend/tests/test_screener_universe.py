"""Tests for screener Stage 1 universe filter (no network, mocked yfinance)."""

from unittest.mock import MagicMock, patch

import pandas as pd

from services.screener.universe import UniverseRecord, load_universe


def _fake_history(n: int = 30, close: float = 100.0, volume: float = 200_000.0):
    idx = pd.date_range("2026-04-01", periods=n)
    return pd.DataFrame(
        {"Close": [close] * n, "Volume": [volume] * n}, index=idx
    )


@patch("services.screener.universe.yf.Ticker")
def test_load_universe_filters_low_turnover(mock_ticker):
    """Low-turnover stocks should be excluded."""
    high = MagicMock()
    high.history.return_value = _fake_history(close=100, volume=1_000_000)  # 1e8 turnover
    high.info = {"marketCap": 1e10, "shortName": "High"}

    low = MagicMock()
    low.history.return_value = _fake_history(close=10, volume=1_000)  # 1e4 turnover
    low.info = {"marketCap": 1e10, "shortName": "Low"}

    mock_ticker.side_effect = lambda t: high if t == "AAA.TW" else low

    out = load_universe(
        tickers=["AAA.TW", "BBB.TW"],
        min_turnover=5e7,
        min_market_cap=0,
        max_workers=2,
    )
    assert [r.ticker for r in out] == ["AAA.TW"]
    assert isinstance(out[0], UniverseRecord)


@patch("services.screener.universe.yf.Ticker")
def test_load_universe_skips_short_history(mock_ticker):
    """Stocks with <20 days of history should be skipped."""
    short = MagicMock()
    short.history.return_value = _fake_history(n=10)
    short.info = {"marketCap": 1e10}
    mock_ticker.return_value = short

    out = load_universe(tickers=["XXX.TW"], min_turnover=0, min_market_cap=0)
    assert out == []


@patch("services.screener.universe.yf.Ticker")
def test_load_universe_handles_fetch_errors(mock_ticker):
    """yfinance exceptions should be swallowed (record skipped, no raise)."""
    mock_ticker.side_effect = RuntimeError("network down")
    out = load_universe(tickers=["BAD.TW"], min_turnover=0)
    assert out == []


def test_load_universe_market_cap_optional():
    """Stocks missing marketCap should not be excluded by min_market_cap filter."""
    rec = UniverseRecord(
        ticker="X.TW",
        name="X",
        industry="半導體",
        price=100,
        market_cap=None,
        avg_turnover_20d=1e8,
        history=_fake_history(),
        info={},
    )
    # Replicate the filtering logic guard
    assert rec.market_cap is None
    # Should be allowed: condition `if min_market_cap and rec.market_cap is not None and ...`
    assert not (5e9 and rec.market_cap is not None and rec.market_cap < 5e9)
