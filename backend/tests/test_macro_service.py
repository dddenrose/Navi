"""Tests for macro_service — 大盤指數、三大法人總額、期貨未平倉。"""

import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.macro_service import (
    FuturesPartyPosition,
    FuturesPositionsData,
    InstitutionalDailyAggregate,
    MarketIndexData,
    _fetch_bfi82u_one_day,
    _fetch_taifex_one_day,
    get_futures_positions,
    get_institutional_aggregate,
    get_market_index,
)


# ── 大盤指數 ─────────────────────────────────────────────────────────────────


class TestMarketIndex:
    def _mis_resp(self, msg_array):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"msgArray": msg_array}
        return m

    def test_mis_taiex_parses(self):
        import services.macro_service as svc

        sample = {
            "n": "發行量加權股價指數", "z": "46076.98", "y": "46459.16",
            "o": "46364.07", "h": "46364.07", "l": "45769.18",
            "d": "20260604", "t": "11:25:40",
        }
        with patch.object(svc.requests, "get", return_value=self._mis_resp([sample])):
            data = svc._fetch_mis_index("TWSE")

        assert data is not None
        assert data.market == "TWSE"
        assert data.name == "發行量加權股價指數"
        assert data.price == 46076.98
        assert data.change == round(46076.98 - 46459.16, 2)
        assert data.change_percent == round((data.change / 46459.16) * 100, 2)
        assert data.is_intraday is True
        assert data.data_source == "MIS"
        assert data.as_of_date == "2026-06-04"
        assert data.as_of_time == "11:25:40"

    def test_mis_uses_otc_for_tpex(self):
        import services.macro_service as svc

        with patch.object(svc.requests, "get", return_value=self._mis_resp([])) as mock_get:
            svc._fetch_mis_index("TPEx")
        params = mock_get.call_args.kwargs["params"]
        assert params["ex_ch"] == "otc_o00.tw"

    def test_mis_unknown_market_returns_none(self):
        import services.macro_service as svc

        assert svc._fetch_mis_index("NASDAQ") is None

    def test_mis_z_dash_falls_back_to_open(self):
        import services.macro_service as svc

        sample = {"n": "x", "z": "-", "y": "100", "o": "99.5", "d": "20260604", "t": "09:00:00"}
        with patch.object(svc.requests, "get", return_value=self._mis_resp([sample])):
            data = svc._fetch_mis_index("TWSE")
        assert data.price == 99.5

    def test_mis_network_error_returns_none(self):
        import services.macro_service as svc

        with patch.object(svc.requests, "get", side_effect=RuntimeError("boom")):
            assert svc._fetch_mis_index("TWSE") is None

    def test_openapi_taiex_parses_minus_change(self):
        import services.macro_service as svc

        rows = [
            {"指數": "其他指數", "收盤指數": "1"},
            {
                "日期": "1150603",
                "指數": "發行量加權股價指數",
                "收盤指數": "46459.16",
                "漲跌": "-",
                "漲跌點數": "100.50",
                "漲跌百分比": "0.22",
            },
        ]
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = rows
        with patch.object(svc.requests, "get", return_value=m):
            data = svc._fetch_openapi_taiex()

        assert data.price == 46459.16
        assert data.change == -100.50
        assert data.change_percent == -0.22
        assert data.is_intraday is False
        assert data.as_of_date == "2026-06-03"
        assert data.data_source == "MI_INDEX"

    def test_get_market_index_falls_back_to_openapi_when_mis_fails(self):
        """TWSE：MIS 失敗時自動 fallback 到 MI_INDEX。"""
        import services.macro_service as svc

        fb = MarketIndexData(
            market="TWSE", name="發行量加權股價指數", price=45000.0,
            change=-50.0, change_percent=-0.11,
            as_of_date="2026-06-03", is_intraday=False, data_source="MI_INDEX",
        )
        with (
            patch.object(svc, "_fetch_mis_index", return_value=None),
            patch.object(svc, "_fetch_openapi_taiex", return_value=fb),
        ):
            data = get_market_index("TWSE")
        assert data.price == 45000.0
        assert data.is_intraday is False
        assert data.data_source == "MI_INDEX"

    def test_get_market_index_tpex_no_fallback(self):
        """TPEx：MIS 失敗時不 fallback（沒有 OpenAPI 替代來源）。"""
        import services.macro_service as svc

        with patch.object(svc, "_fetch_mis_index", return_value=None):
            data = get_market_index("TPEx")
        assert data.price is None
        assert data.error is not None


# ── 三大法人買賣超彙總 ──────────────────────────────────────────────────────


class TestInstitutionalAggregate:
    def _bfi82u_ok(self, day_str="20260603"):
        return {
            "stat": "OK",
            "date": day_str,
            "fields": ["單位名稱", "買進金額", "賣出金額", "買賣差額"],
            "data": [
                ["自營商(自行買賣)", "11,381,726,498", "8,430,164,554", "2,951,561,944"],
                ["自營商(避險)", "39,333,229,103", "39,688,024,805", "-354,795,702"],
                ["投信", "67,609,302,240", "62,057,732,108", "5,551,570,132"],
                ["外資及陸資(不含外資自營商)", "100,000,000,000", "60,000,000,000", "40,000,000,000"],
                ["外資自營商", "1,000", "500", "500"],
                ["合計", "0", "0", "48,148,336,874"],
            ],
        }

    def _bfi82u_no_data(self):
        return {"stat": "很抱歉，沒有符合條件的資料!", "data": []}

    def test_fetch_one_day_parses_all_parties(self):
        import services.macro_service as svc

        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = self._bfi82u_ok()
        with patch.object(svc.requests, "get", return_value=m):
            rec = _fetch_bfi82u_one_day(date(2026, 6, 3))

        assert rec is not None
        assert rec.date == "2026-06-03"
        assert rec.dealer_self_net == 2_951_561_944
        assert rec.dealer_hedge_net == -354_795_702
        assert rec.investment_trust_net == 5_551_570_132
        assert rec.foreign_net == 40_000_000_000
        assert rec.foreign_dealer_net == 500
        assert rec.total_net == 48_148_336_874
        assert rec.dealer_net == 2_951_561_944 - 354_795_702
        assert rec.foreign_total_net == 40_000_000_000 + 500

    def test_fetch_one_day_skips_when_no_data(self):
        import services.macro_service as svc

        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = self._bfi82u_no_data()
        with patch.object(svc.requests, "get", return_value=m):
            assert _fetch_bfi82u_one_day(date(2026, 5, 30)) is None

    def test_fetch_one_day_handles_network_error(self):
        import services.macro_service as svc

        with patch.object(svc.requests, "get", side_effect=RuntimeError("boom")):
            assert _fetch_bfi82u_one_day(date(2026, 6, 3)) is None

    def test_aggregate_collects_n_trading_days_skipping_holidays(self):
        """週四查 3 日；6/1 假裝無資料（連假最後一天）→ 跳過往更早找。"""
        import services.macro_service as svc

        rec_603 = InstitutionalDailyAggregate(date="2026-06-03", foreign_net=100)
        rec_602 = InstitutionalDailyAggregate(date="2026-06-02", foreign_net=200)
        rec_529 = InstitutionalDailyAggregate(date="2026-05-29", foreign_net=300)

        def fake_fetch(d: date):
            mapping = {
                date(2026, 6, 3): rec_603,
                date(2026, 6, 2): rec_602,
                date(2026, 5, 29): rec_529,
            }
            return mapping.get(d)

        class FakeDT:
            @classmethod
            def now(cls, tz):
                return datetime(2026, 6, 4, 10, 0, tzinfo=tz)

        with (
            patch.object(svc, "_fetch_bfi82u_one_day", side_effect=fake_fetch),
            patch.object(svc, "datetime", FakeDT),
        ):
            data = get_institutional_aggregate(days=3)

        assert data.error is None
        assert len(data.records) == 3
        assert [r.date for r in data.records] == ["2026-06-03", "2026-06-02", "2026-05-29"]

    def test_aggregate_returns_error_when_all_fail(self):
        import services.macro_service as svc

        with patch.object(svc, "_fetch_bfi82u_one_day", return_value=None):
            data = get_institutional_aggregate(days=2)
        assert data.error is not None
        assert data.records == []

    def test_aggregate_clamps_days(self):
        """days 超過上限 20 時被截斷；嘗試上限合理。"""
        import services.macro_service as svc

        with patch.object(svc, "_fetch_bfi82u_one_day", return_value=None) as mock_fetch:
            get_institutional_aggregate(days=999)
        # max_attempts = 20*3 + 5 = 65
        assert mock_fetch.call_count <= 65


# ── 期貨三大法人 ────────────────────────────────────────────────────────────


_TAIFEX_SAMPLE_CSV = (
    "日期,商品名稱,身份別,多方交易口數,多方交易契約金額(千元),空方交易口數,"
    "空方交易契約金額(千元),多空交易口數淨額,多空交易契約金額淨額(千元),"
    "多方未平倉口數,多方未平倉契約金額(千元),空方未平倉口數,"
    "空方未平倉契約金額(千元),多空未平倉口數淨額,多空未平倉契約金額淨額(千元)\n"
    "2026/06/03,臺股期貨,自營商,6391,59718624,6420,59993729,-29,-275105,"
    "6981,65510088,4507,42336826,2474,23173262\n"
    "2026/06/03,臺股期貨,投信,1630,15277478,91,852449,1539,14425029,"
    "56541,529868336,5237,49078022,51304,480790314\n"
    "2026/06/03,臺股期貨,外資及陸資,52717,491986093,52540,490327675,177,1658418,"
    "15473,145006636,82245,770823207,-66772,-625816571\n"
)


class TestFuturesPositions:
    def _make_resp(self, body_bytes: bytes):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.content = body_bytes
        return m

    def test_taifex_parses_three_parties(self):
        import services.macro_service as svc

        body = _TAIFEX_SAMPLE_CSV.encode("ms950")
        with patch.object(svc.requests, "post", return_value=self._make_resp(body)):
            data = _fetch_taifex_one_day("TXF", date(2026, 6, 3))

        assert data is not None
        assert data.commodity == "TXF"
        assert data.commodity_name == "臺股期貨"
        assert data.date == "2026-06-03"
        assert len(data.parties) == 3

        by_party = {p.party: p for p in data.parties}
        d = by_party["自營商"]
        assert d.long_oi_lots == 6981
        assert d.short_oi_lots == 4507
        assert d.net_oi_lots == 2474
        assert d.net_trade_lots == -29

        f = by_party["外資及陸資"]
        assert f.long_oi_lots == 15473
        assert f.short_oi_lots == 82245
        assert f.net_oi_lots == -66772
        assert f.net_trade_lots == 177

    def test_taifex_html_response_means_no_data(self):
        """查無資料時，TAIFEX 回傳 HTML alert 頁面；應 parse 成 None。"""
        import services.macro_service as svc

        html = b"<!DOCTYPE HTML><html><body>alert</body></html>"
        with patch.object(svc.requests, "post", return_value=self._make_resp(html)):
            assert _fetch_taifex_one_day("TXF", date(2026, 5, 30)) is None

    def test_taifex_network_error_returns_none(self):
        import services.macro_service as svc

        with patch.object(svc.requests, "post", side_effect=RuntimeError("boom")):
            assert _fetch_taifex_one_day("TXF", date(2026, 6, 3)) is None

    def test_taifex_sends_correct_form_payload(self):
        import services.macro_service as svc

        body = _TAIFEX_SAMPLE_CSV.encode("ms950")
        with patch.object(svc.requests, "post", return_value=self._make_resp(body)) as mock_post:
            _fetch_taifex_one_day("MXF", date(2026, 6, 3))
        sent = mock_post.call_args.kwargs["data"]
        assert sent["queryStartDate"] == "2026/06/03"
        assert sent["queryEndDate"] == "2026/06/03"
        assert sent["commodityId"] == "MXF"

    def test_get_futures_positions_walks_back_until_found(self):
        """假裝今天無資料，前一交易日才有；應自動往回找。"""
        import services.macro_service as svc

        good = FuturesPositionsData(
            commodity="TXF", commodity_name="臺股期貨", date="2026-06-03",
            parties=[FuturesPartyPosition(party="外資及陸資", net_oi_lots=-1000)],
        )
        call_log: list[date] = []

        def fake_fetch(c: str, d: date):
            call_log.append(d)
            return good if d == date(2026, 6, 3) else None

        class FakeDT:
            @classmethod
            def now(cls, tz):
                return datetime(2026, 6, 4, 12, 0, tzinfo=tz)

        with (
            patch.object(svc, "_fetch_taifex_one_day", side_effect=fake_fetch),
            patch.object(svc, "datetime", FakeDT),
        ):
            data = get_futures_positions("TXF")

        assert data.error is None
        assert data.date == "2026-06-03"
        assert call_log[0] == date(2026, 6, 4)
        assert date(2026, 6, 3) in call_log

    def test_get_futures_positions_returns_error_after_exhausting_attempts(self):
        import services.macro_service as svc

        with patch.object(svc, "_fetch_taifex_one_day", return_value=None):
            data = get_futures_positions("TXF")
        assert data.error is not None
        assert data.parties == []

    def test_get_futures_positions_normalizes_commodity_to_upper(self):
        import services.macro_service as svc

        captured = []

        def fake_fetch(c, d):
            captured.append(c)
            return None

        with patch.object(svc, "_fetch_taifex_one_day", side_effect=fake_fetch):
            get_futures_positions("txf")
        assert all(c == "TXF" for c in captured)
