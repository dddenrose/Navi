"""月營收 daily TTL 快取層測試（個股單檔查詢用，獨立於既有的
test_screener_monthly_revenue.py，不影響 screener 既有行為）。"""

from unittest.mock import MagicMock, patch

from services.screener import monthly_revenue as mr

_SAMPLE_ROWS = [
    {
        "資料年月": "11506",
        "公司代號": "2330",
        "公司名稱": "台積電",
        "營業收入-當月營收": "263711798",
        "營業收入-上月比較增減(%)": "5.5",
        "營業收入-去年同月增減(%)": "30.09498020271696",
        "累計營業收入-前期比較增減(%)": "28.4",
    },
    {
        "資料年月": "11506",
        "公司代號": "1101",
        "公司名稱": "台泥",
        "營業收入-當月營收": "13382706",
        "營業收入-上月比較增減(%)": "6.110785011084273",
        "營業收入-去年同月增減(%)": "32.39878166305348",
        "累計營業收入-前期比較增減(%)": "1.5436229900730476",
    },
]


def _mock_response(rows):
    resp = MagicMock()
    resp.json.return_value = rows
    resp.raise_for_status.return_value = None
    return resp


def setup_function(_fn):
    """每個測試前重置 module-level 快取，避免測試間互相污染。"""
    mr._bulk_cache = None
    mr._bulk_cache_time = 0.0


def test_new_fields_parsed_alongside_existing_yoy_label():
    """擴充後的 dataclass 欄位（revenue/mom/yoy_acc）正確解析，且既有欄位不受影響。"""
    with patch("services.screener.monthly_revenue.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_SAMPLE_ROWS)
        out = mr.fetch_monthly_revenue_bulk()

    tsmc = out["2330"]
    assert tsmc.revenue == 263711798
    assert abs(tsmc.mom - 0.055) < 1e-6
    assert abs(tsmc.yoy_acc - 0.284) < 1e-6
    assert abs(tsmc.yoy - 0.3009498) < 1e-4
    assert tsmc.label == "115年6月"


def test_missing_new_fields_default_to_none():
    """既有測試 fixture 缺新欄位時（沿用舊格式），新欄位需優雅回 None 不炸。"""
    rows_without_new_fields = [
        {
            "資料年月": "11505",
            "公司代號": "2330",
            "公司名稱": "台積電",
            "營業收入-去年同月增減(%)": "30.0",
        }
    ]
    with patch("services.screener.monthly_revenue.requests.get") as mock_get:
        mock_get.return_value = _mock_response(rows_without_new_fields)
        out = mr.fetch_monthly_revenue_bulk()

    assert out["2330"].revenue is None
    assert out["2330"].mom is None
    assert out["2330"].yoy_acc is None
    assert out["2330"].yoy == 0.30  # 既有欄位行為不變


def test_bulk_cached_only_calls_network_once():
    """daily TTL 快取：連續呼叫 fetch_monthly_revenue_bulk_cached() 只打一次外部 API。"""
    with patch("services.screener.monthly_revenue.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_SAMPLE_ROWS)
        first = mr.fetch_monthly_revenue_bulk_cached()
        second = mr.fetch_monthly_revenue_bulk_cached()

    assert mock_get.call_count == 1
    assert first is second
    assert first["2330"].revenue == 263711798


def test_get_monthly_revenue_single_ticker_lookup():
    """單檔查詢：ticker 可含 .TW 後綴，從快取取正確值。"""
    with patch("services.screener.monthly_revenue.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_SAMPLE_ROWS)
        result = mr.get_monthly_revenue("2330.TW")

    assert mock_get.call_count == 1
    assert result is not None
    assert result.code == "2330"
    assert result.revenue == 263711798
    assert result.label == "115年6月"


def test_get_monthly_revenue_otc_ticker_returns_none_without_network_call():
    """.TWO（上櫃）無此 API，應直接回 None，不觸發任何網路請求。"""
    with patch("services.screener.monthly_revenue.requests.get") as mock_get:
        result = mr.get_monthly_revenue("6488.TWO")
    assert result is None
    mock_get.assert_not_called()


def test_get_monthly_revenue_ticker_not_found_returns_none():
    with patch("services.screener.monthly_revenue.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_SAMPLE_ROWS)
        result = mr.get_monthly_revenue("9999.TW")
    assert result is None


def test_bulk_cache_keeps_stale_data_on_network_failure():
    """快取過期後若重新抓取失敗，應保留舊快取而非清空（呼叫端才不會突然拿不到資料）。"""
    with patch("services.screener.monthly_revenue.requests.get") as mock_get:
        mock_get.return_value = _mock_response(_SAMPLE_ROWS)
        first = mr.fetch_monthly_revenue_bulk_cached()

    # 模擬快取過期
    mr._bulk_cache_time = 0.0

    with patch(
        "services.screener.monthly_revenue.requests.get",
        side_effect=ConnectionError("boom"),
    ):
        second = mr.fetch_monthly_revenue_bulk_cached()

    assert second == first
    assert second["2330"].revenue == 263711798
