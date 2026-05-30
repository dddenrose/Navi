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

    def test_us_overview_has_intraday_flag(self):
        with patch("services.stock_service.yf.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.info = {
                "shortName": "Apple Inc.",
                "currentPrice": 150.0,
                "previousClose": 148.0,
                "currency": "USD",
            }
            mock_ticker_cls.return_value = mock_ticker
            result = get_stock_overview("AAPL")
        assert result.data_source == "yfinance"
        assert result.is_intraday is True
        assert result.as_of_date == ""

    def test_tw_overview_uses_open_api(self):
        """台股 .TW 應走 TWSE Open API，不依賴 yfinance 的價格欄位。"""
        from datetime import date

        import services.stock_service as svc

        quote = svc._TWQuote(
            code="2330",
            name="台積電",
            market=".TW",
            close=580.0,
            change=2.0,
            volume_shares=28_156_000,
        )
        with (
            patch.object(svc, "_fetch_tw_quotes", return_value={"2330": quote}),
            patch.object(svc, "_get_ticker_info", return_value={"marketCap": 15_000_000_000_000}),
            patch.object(svc, "_latest_tw_trading_date", return_value=date(2026, 5, 26)),
        ):
            result = svc.get_stock_overview("2330.TW")

        assert result.price == 580.0
        assert result.change == 2.0
        assert result.change_percent == pytest.approx(0.35, abs=0.01)
        assert result.currency == "TWD"
        assert result.data_source == "TWSE"
        assert result.is_intraday is False
        assert result.as_of_date == "2026-05-26"
        assert result.market_cap == 15_000_000_000_000  # yfinance 補強欄位

    def test_tw_overview_missing_returns_empty(self):
        """TWSE/TPEx 抓不到該檔時不可 fallback 到 yfinance；明確回傳 price=None。"""
        import services.stock_service as svc

        with patch.object(svc, "_fetch_tw_quotes", return_value={}):
            result = svc.get_stock_overview("9999.TW")

        assert result.price is None
        assert result.data_source == ""


# ── TWSE Open API helpers ────────────────────────────────────────────────────


class TestTWHelpers:
    def test_safe_float_handles_dash_and_empty(self):
        from services.stock_service import _safe_float

        assert _safe_float("580.00") == 580.0
        assert _safe_float("-") is None
        assert _safe_float("") is None
        assert _safe_float(None) is None
        assert _safe_float("1,234.5") == 1234.5
        assert _safe_float(123) == 123.0

    def test_latest_tw_trading_date_weekday_after_close(self):
        from datetime import datetime

        from services.stock_service import _TPE_TZ, _latest_tw_trading_date

        # 週三 15:00 → 當天
        wed = datetime(2026, 5, 27, 15, 0, tzinfo=_TPE_TZ)
        assert _latest_tw_trading_date(wed).isoformat() == "2026-05-27"

    def test_latest_tw_trading_date_weekday_before_close(self):
        from datetime import datetime

        from services.stock_service import _TPE_TZ, _latest_tw_trading_date

        # 週三 10:00 → 回退到週二
        wed_morning = datetime(2026, 5, 27, 10, 0, tzinfo=_TPE_TZ)
        assert _latest_tw_trading_date(wed_morning).isoformat() == "2026-05-26"

    def test_latest_tw_trading_date_weekend(self):
        from datetime import datetime

        from services.stock_service import _TPE_TZ, _latest_tw_trading_date

        # 週日 → 回退到週五
        sun = datetime(2026, 5, 24, 10, 0, tzinfo=_TPE_TZ)
        assert _latest_tw_trading_date(sun).isoformat() == "2026-05-22"


# ── TW Quote Provider 抽象 ─────────────────────────────────────────────────


class TestTWQuoteProvider:
    def test_default_provider_is_openapi(self):
        import services.stock_service as svc

        from config import settings

        original = settings.tw_quote_provider
        try:
            settings.tw_quote_provider = ""
            assert svc._select_tw_provider().name == "openapi"
            settings.tw_quote_provider = "unknown_xyz"
            assert svc._select_tw_provider().name == "openapi"
        finally:
            settings.tw_quote_provider = original

    def test_select_mis_provider(self):
        import services.stock_service as svc

        from config import settings

        original = settings.tw_quote_provider
        try:
            settings.tw_quote_provider = "mis"
            p = svc._select_tw_provider()
            assert p.name == "mis"
            assert p.is_intraday is True
            assert p.display_label == "MIS"
        finally:
            settings.tw_quote_provider = original

    def test_mis_provider_parses_response(self):
        """MisProvider 正確解析 MIS msgArray、處理張→股轉換、日期格式。"""
        import services.stock_service as svc

        fake_resp = MagicMock()
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json.return_value = {
            "msgArray": [
                {
                    "c": "0050", "n": "元大台灣50",
                    "z": "105.4000", "y": "100.5000",
                    "o": "103.20", "h": "105.40", "l": "102.70",
                    "v": "102355", "d": "20260529", "t": "13:30:00", "ex": "tse",
                }
            ]
        }
        with patch.object(svc.requests, "get", return_value=fake_resp) as mock_get:
            q = svc.MisProvider().get_quote("0050", ".TW")

        assert q is not None
        assert q.code == "0050"
        assert q.name == "元大台灣50"
        assert q.close == 105.4
        assert q.change == round(105.4 - 100.5, 2)
        assert q.open == 103.20
        assert q.volume_shares == 102355 * 1000  # 張 → 股
        assert q.date == "2026-05-29"
        # 確認帶了正確的 ex_ch（上市 → tse_）
        called_params = mock_get.call_args.kwargs.get("params", {})
        assert called_params.get("ex_ch") == "tse_0050.tw"

    def test_mis_provider_uses_otc_for_two(self):
        import services.stock_service as svc

        fake_resp = MagicMock()
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json.return_value = {"msgArray": []}
        with patch.object(svc.requests, "get", return_value=fake_resp) as mock_get:
            svc.MisProvider().get_quote("6488", ".TWO")
        assert mock_get.call_args.kwargs["params"]["ex_ch"] == "otc_6488.tw"

    def test_mis_provider_handles_network_error(self):
        """網路失敗時回傳 None，不丟例外。"""
        import services.stock_service as svc

        with patch.object(svc.requests, "get", side_effect=RuntimeError("timeout")):
            assert svc.MisProvider().get_quote("0050", ".TW") is None

    def test_overview_falls_back_to_openapi_when_mis_fails(self):
        """選擇 MIS 但失敗時，應 fallback 到 OpenAPI 快取。"""
        import services.stock_service as svc

        from config import settings

        openapi_quote = svc._TWQuote(
            code="2330", name="台積電", market=".TW",
            close=1000.0, change=10.0, volume_shares=12_345_000,
            date="2026-05-28",
        )
        original = settings.tw_quote_provider
        try:
            settings.tw_quote_provider = "mis"
            with (
                patch.object(svc, "_fetch_tw_quotes", return_value={"2330": openapi_quote}),
                patch.dict(svc._tw_listing_market, {"2330": ".TW"}, clear=False),
                patch.object(svc.MisProvider, "get_quote", return_value=None),
                patch.object(svc, "_get_ticker_info", return_value={}),
            ):
                result = svc.get_stock_overview("2330.TW")
            assert result.price == 1000.0
            assert result.data_source == "TWSE"  # fallback 後回到 openapi 的市場 label
            assert result.is_intraday is False
        finally:
            settings.tw_quote_provider = original


# ── get_technical_indicators ─────────────────────────────────────────────────


class TestGetTechnicalIndicators:
    @patch("services.stock_service.yf.Ticker")
    def test_with_sufficient_data(self, mock_ticker_cls):
        import numpy as np
        import pandas as pd

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
            ticker="TSM",
            name="TSMC",
            price=180.5,
            change=2.5,
            change_percent=1.4,
            volume=10_000_000,
            market_cap=900_000_000_000,
            currency="USD",
        )
        technical = TechnicalIndicators(
            ticker="TSM",
            current_price=180.5,
            ma5=179.0,
            ma10=177.0,
            ma20=175.0,
            ma60=170.0,
            ma_trend="多頭排列",
            rsi_14=62.4,
            rsi_signal="中性",
            macd=1.5,
            macd_signal=1.2,
            macd_histogram=0.3,
            macd_cross="多方（DIF > DEA）",
            k_value=68.0,
            d_value=55.0,
            kd_signal="中性",
            bb_upper=185.0,
            bb_middle=175.0,
            bb_lower=165.0,
            bb_position="中軌與上軌之間（偏多）",
            summary="📈 偏多（3多/0空）",
        )
        fundamental = FundamentalData(
            ticker="TSM",
            name="TSMC",
            pe_ratio=25.3,
            roe=0.284,
            eps=6.5,
            sector="Technology",
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
