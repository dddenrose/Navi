"""TWSE OpenAPI 月營收 fetcher 的解析測試（網路層 mock）."""

from unittest.mock import MagicMock, patch

from services.screener.monthly_revenue import (
    _format_label,
    _parse_yoy,
    fetch_monthly_revenue_bulk,
)

_SAMPLE_ROWS = [
    {
        "資料年月": "11505",
        "公司代號": "2330",
        "公司名稱": "台積電",
        "營業收入-去年同月增減(%)": "30.09498020271696",
    },
    {
        "資料年月": "11505",
        "公司代號": "1101",
        "公司名稱": "台泥",
        "營業收入-去年同月增減(%)": "-0.059289218784111405",
    },
    {  # YoY 缺值（新上市 / 停徵）
        "資料年月": "11505",
        "公司代號": "9999",
        "公司名稱": "測試",
        "營業收入-去年同月增減(%)": None,
    },
]


def _mock_response(rows):
    resp = MagicMock()
    resp.json.return_value = rows
    resp.raise_for_status.return_value = None
    return resp


def test_parse_yoy_percent_string_to_decimal():
    assert _parse_yoy("30.0") == 0.30
    assert _parse_yoy("-5.5") == -0.055
    assert _parse_yoy(None) is None
    assert _parse_yoy("N/A") is None


def test_format_label_roc_ym():
    assert _format_label("11505") == "115年5月"
    assert _format_label("11512") == "115年12月"
    assert _format_label("garbage") == "garbage"


def test_fetch_bulk_maps_by_bare_code():
    with patch("services.screener.monthly_revenue.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_SAMPLE_ROWS)
        out = fetch_monthly_revenue_bulk()
    assert out["2330"].yoy is not None
    assert abs(out["2330"].yoy - 0.3009498) < 1e-4
    assert out["2330"].label == "115年5月"
    assert out["1101"].yoy < 0
    assert out["9999"].yoy is None  # 缺 YoY 不炸，label 仍在


def test_fetch_bulk_network_failure_returns_empty():
    with patch(
        "services.screener.monthly_revenue.requests.get",
        side_effect=ConnectionError("boom"),
    ):
        assert fetch_monthly_revenue_bulk() == {}
