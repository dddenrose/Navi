"""產業 PE 分位數服務測試：統計計算、細分類/大類 fallback、樣本不足處理。"""

from unittest.mock import patch

from services import industry_valuation_service as ivs
from services.screener.industry_mapper import FALLBACK_INDUSTRY


def setup_function(_fn):
    """每個測試前重置 module-level 快取，避免測試間互相污染。"""
    ivs._stats_cache = None
    ivs._stats_cache_time = 0.0


def test_safe_pe_filters_blank_dash_and_out_of_range():
    assert ivs._safe_pe("") is None  # BWIBBU 缺值以空字串表示
    assert ivs._safe_pe("-") is None
    assert ivs._safe_pe(None) is None
    assert ivs._safe_pe("not-a-number") is None
    assert ivs._safe_pe("0") is None  # 排除 <=0
    assert ivs._safe_pe("150") is None  # 排除極端離群值 (>=100)
    assert ivs._safe_pe("18.5") == 18.5


def test_percentile_rank_basic():
    values = [10.0, 12.0, 14.0, 16.0, 18.0]
    # target 為清單中的最小值：0 個更低、1 個相等(自己) -> (0+0.5)/5*100 = 10.0
    assert ivs._percentile_rank(values, 10.0) == 10.0
    # target 為清單中的最大值：4 個更低、1 個相等(自己) -> (4+0.5)/5*100 = 90.0
    assert ivs._percentile_rank(values, 18.0) == 90.0
    assert ivs._percentile_rank([], 10.0) == 50.0  # 空清單防呆


def _six_codes_pe():
    """6 檔標的，PE 由 10 到 20 均分。"""
    return {str(1000 + i): float(10 + i * 2) for i in range(6)}


@patch("services.industry_valuation_service.get_industry")
@patch("services.industry_valuation_service.get_fine_industry")
@patch("services.industry_valuation_service._fetch_bwibbu_bulk")
def test_uses_fine_industry_when_sample_sufficient(mock_fetch, mock_fine, mock_coarse):
    pe_map = _six_codes_pe()  # target "1005" pe=20.0 (最高)
    mock_fetch.return_value = pe_map
    mock_fine.return_value = "半導體業"  # 全部同一細分類 -> 樣本數 6 >= MIN_PE_SAMPLE
    mock_coarse.return_value = "電子科技"

    result = ivs.get_industry_pe("1005.TW")

    assert result is not None
    assert result.sample_size == 6
    assert "半導體業" in result.industry
    assert "細分類" in result.industry
    assert result.stock_pe == 20.0
    assert result.median_pe == 15.0
    # 5 檔更低、自己相等 1 檔 -> (5+0.5)/6*100 = 91.7
    assert result.percentile == 91.7


@patch("services.industry_valuation_service.get_industry")
@patch("services.industry_valuation_service.get_fine_industry")
@patch("services.industry_valuation_service._fetch_bwibbu_bulk")
def test_falls_back_to_coarse_when_fine_sample_insufficient(mock_fetch, mock_fine, mock_coarse):
    pe_map = _six_codes_pe()  # target "1000"

    def fine_side_effect(ticker):
        code = ticker.split(".")[0]
        # 只有目標自己在這個細分類，樣本數 1 < MIN_PE_SAMPLE -> 應 fallback
        return "冷門利基業" if code == "1000" else "其他細產業"

    def coarse_side_effect(ticker):
        return "電子科技"  # 全部同一大類 -> 樣本數 6 >= MIN_PE_SAMPLE

    mock_fetch.return_value = pe_map
    mock_fine.side_effect = fine_side_effect
    mock_coarse.side_effect = coarse_side_effect

    result = ivs.get_industry_pe("1000.TW")

    assert result is not None
    assert result.sample_size == 6
    assert "電子科技" in result.industry
    assert "大類" in result.industry


@patch("services.industry_valuation_service.get_industry")
@patch("services.industry_valuation_service.get_fine_industry")
@patch("services.industry_valuation_service._fetch_bwibbu_bulk")
def test_returns_none_when_both_fine_and_coarse_insufficient(mock_fetch, mock_fine, mock_coarse):
    pe_map = _six_codes_pe()

    def fine_side_effect(ticker):
        code = ticker.split(".")[0]
        return "冷門利基業" if code == "1000" else "其他細產業"

    mock_fetch.return_value = pe_map
    mock_fine.side_effect = fine_side_effect
    mock_coarse.return_value = FALLBACK_INDUSTRY  # 「公用其他」不作為估值錨

    result = ivs.get_industry_pe("1000.TW")

    assert result is None


@patch("services.industry_valuation_service._fetch_bwibbu_bulk")
def test_otc_ticker_returns_none_without_network_call(mock_fetch):
    result = ivs.get_industry_pe("6488.TWO")
    assert result is None
    mock_fetch.assert_not_called()


@patch("services.industry_valuation_service.get_industry")
@patch("services.industry_valuation_service.get_fine_industry")
@patch("services.industry_valuation_service._fetch_bwibbu_bulk")
def test_ticker_with_no_pe_data_returns_none(mock_fetch, mock_fine, mock_coarse):
    mock_fetch.return_value = _six_codes_pe()  # 不含 "9999"
    mock_fine.return_value = "半導體業"
    mock_coarse.return_value = "電子科技"

    result = ivs.get_industry_pe("9999.TW")

    assert result is None


@patch("services.industry_valuation_service.get_industry")
@patch("services.industry_valuation_service.get_fine_industry")
@patch("services.industry_valuation_service._fetch_bwibbu_bulk")
def test_stats_cached_only_fetches_network_once(mock_fetch, mock_fine, mock_coarse):
    mock_fetch.return_value = _six_codes_pe()
    mock_fine.return_value = "半導體業"
    mock_coarse.return_value = "電子科技"

    ivs.get_industry_pe("1000.TW")
    ivs.get_industry_pe("1001.TW")

    assert mock_fetch.call_count == 1


@patch("services.industry_valuation_service._fetch_bwibbu_bulk", return_value={})
def test_network_failure_returns_none(mock_fetch):
    result = ivs.get_industry_pe("2330.TW")
    assert result is None
