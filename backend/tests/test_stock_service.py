"""Tests for stock_service — yfinance integration, technical indicators, fundamentals."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.stock_service import (
    FundamentalData,
    StockOverviewData,
    TechnicalIndicators,
    format_stock_data_for_prompt,
    get_fundamental_data,
    get_stock_overview,
    get_technical_indicators,
    normalize_ticker,
)


# ── normalize_ticker ─────────────────────────────────────────────────────────


class TestNormalizeTicker:
    def test_chinese_name(self):
        assert normalize_ticker("台積電") == "2330.TW"
        assert normalize_ticker("鴻海") == "2317.TW"

    def test_dollar_prefix(self):
        assert normalize_ticker("$TSMC") == "TSMC"
        assert normalize_ticker("$AAPL") == "AAPL"

    def test_pure_number_tw(self):
        assert normalize_ticker("2330") == "2330.TW"
        assert normalize_ticker("2317") == "2317.TW"

    def test_already_tw(self):
        assert normalize_ticker("2330.TW") == "2330.TW"
        assert normalize_ticker("6547.TWO") == "6547.TWO"

    def test_us_ticker(self):
        assert normalize_ticker("AAPL") == "AAPL"
        assert normalize_ticker("TSM") == "TSM"

    def test_whitespace(self):
        assert normalize_ticker("  AAPL  ") == "AAPL"

    def test_case_insensitive(self):
        assert normalize_ticker("aapl") == "AAPL"


# ── get_stock_overview ───────────────────────────────────────────────────────


class TestGetStockOverview:
    @patch("services.stock_service.yf.Ticker")
    def test_basic_overview(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "shortName": "Apple Inc.",
            "currentPrice": 150.0,
            "previousClose": 148.0,
            "volume": 5_000_000,
            "marketCap": 2_500_000_000_000,
            "currency": "USD",
            "exchange": "NMS",
        }
        mock_ticker_cls.return_value = mock_ticker

        result = get_stock_overview("AAPL")

        assert result.name == "Apple Inc."
        assert result.price == 150.0
        assert result.change == 2.0
        assert result.change_percent == pytest.approx(1.35, abs=0.01)
        assert result.volume == 5_000_000
        assert result.currency == "USD"

    @patch("services.stock_service.yf.Ticker")
    def test_missing_data(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker_cls.return_value = mock_ticker

        result = get_stock_overview("UNKNOWN")
        assert result.price is None
        assert result.change is None


# ── get_technical_indicators ─────────────────────────────────────────────────


class TestGetTechnicalIndicators:
    @patch("services.stock_service.yf.Ticker")
    def test_with_sufficient_data(self, mock_ticker_cls):
        import pandas as pd
        import numpy as np

        # Generate 60+ days of fake price data
        np.random.seed(42)
        dates = pd.date_range("2025-12-01", periods=65, freq="B")
        base_price = 100 + np.cumsum(np.random.randn(65) * 0.5)
        df = pd.DataFrame(
            {
                "Open": base_price - 0.5,
                "High": base_price + 1,
                "Low": base_price - 1,
                "Close": base_price,
                "Volume": np.random.randint(1_000_000, 10_000_000, 65),
            },
            index=dates,
        )

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        result = get_technical_indicators("AAPL")

        # Check that all indicators are populated
        assert result.current_price is not None
        assert result.ma5 is not None
        assert result.ma20 is not None
        assert result.ma60 is not None
        assert result.rsi_14 is not None
        assert 0 <= result.rsi_14 <= 100
        assert result.macd is not None
        assert result.k_value is not None
        assert result.bb_upper is not None
        assert result.bb_middle is not None
        assert result.bb_lower is not None
        assert result.bb_upper > result.bb_middle > result.bb_lower
        assert result.summary != ""
        assert result.ma_trend in ("多頭排列", "空頭排列", "糾結")

    @patch("services.stock_service.yf.Ticker")
    def test_insufficient_data(self, mock_ticker_cls):
        import pandas as pd

        df = pd.DataFrame(
            {"Open": [1], "High": [2], "Low": [0.5], "Close": [1.5], "Volume": [100]},
            index=pd.date_range("2026-01-01", periods=1),
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        result = get_technical_indicators("XX")
        assert result.current_price is None  # Insufficient data


# ── get_fundamental_data ─────────────────────────────────────────────────────


class TestGetFundamentalData:
    @patch("services.stock_service.yf.Ticker")
    def test_fundamental_fields(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "shortName": "Test Corp",
            "trailingPE": 25.3,
            "forwardPE": 22.1,
            "priceToBook": 5.5,
            "returnOnEquity": 0.284,
            "returnOnAssets": 0.12,
            "profitMargins": 0.35,
            "trailingEps": 6.5,
            "revenueGrowth": 0.35,
            "sector": "Technology",
            "industry": "Semiconductors",
        }
        mock_ticker_cls.return_value = mock_ticker

        result = get_fundamental_data("TSM")

        assert result.pe_ratio == 25.3
        assert result.roe == 0.284
        assert result.sector == "Technology"
        assert result.revenue_growth == 0.35


# ── format_stock_data_for_prompt ─────────────────────────────────────────────


class TestFormatStockData:
    def test_formatting(self):
        overview = StockOverviewData(
            ticker="TSM", name="TSMC", price=180.5, change=2.5, change_percent=1.4,
            volume=10_000_000, market_cap=900_000_000_000, currency="USD",
        )
        technical = TechnicalIndicators(
            ticker="TSM", current_price=180.5,
            ma5=179.0, ma10=177.0, ma20=175.0, ma60=170.0, ma_trend="多頭排列",
            rsi_14=62.4, rsi_signal="中性",
            macd=1.5, macd_signal=1.2, macd_histogram=0.3, macd_cross="多方（DIF > DEA）",
            k_value=68.0, d_value=55.0, kd_signal="中性",
            bb_upper=185.0, bb_middle=175.0, bb_lower=165.0, bb_position="中軌與上軌之間（偏多）",
            summary="📈 偏多（3多/0空）",
        )
        fundamental = FundamentalData(
            ticker="TSM", name="TSMC",
            pe_ratio=25.3, roe=0.284, eps=6.5, sector="Technology",
            industry="Semiconductors",
        )

        text = format_stock_data_for_prompt(overview, technical, fundamental)
        assert "TSMC" in text
        assert "180.5" in text
        assert "多頭排列" in text
        assert "RSI" in text
        assert "MACD" in text
        assert "25.3" in text  # PE
        assert "Technology" in text
