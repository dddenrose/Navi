"""三個新增個股路由的契約測試（TestClient）：新聞、月營收快照、產業 PE 分位數。

網路層一律 mock（RSS / TWSE OpenAPI），auth 以既有的 dev-mode bypass
（settings.auth_required = False）繞過，不影響其他測試模組。
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app
from services import news_service
from services.industry_valuation_service import IndustryPeResult
from services.screener.monthly_revenue import MonthlyRevenue
from services.stock_service import StockOverviewData

client = TestClient(app)


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)


@pytest.fixture(autouse=True)
def _clear_news_cache():
    news_service._stock_news_cache.clear()
    yield
    news_service._stock_news_cache.clear()


# ── /api/stock/{ticker}/news ─────────────────────────────────────────────────

_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <item>
    <title>新聞標題一</title>
    <link>https://example.com/a</link>
    <source url="https://a.example.com">來源A</source>
    <pubDate>Mon, 01 Jun 2026 09:00:00 GMT</pubDate>
  </item>
  <item>
    <title>新聞標題二</title>
    <link>https://example.com/b</link>
    <source url="https://b.example.com">來源B</source>
    <pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate>
  </item>
  <item>
    <title>新聞標題三</title>
    <link>https://example.com/c</link>
    <source url="https://c.example.com">來源C</source>
    <pubDate>Mon, 01 Jun 2026 07:00:00 GMT</pubDate>
  </item>
</channel>
</rss>"""


@patch("api.routes.stock.get_stock_overview")
def test_news_route_parses_rss_and_respects_limit(mock_overview):
    mock_overview.return_value = StockOverviewData(ticker="2330.TW", name="台積電")

    fake_resp = MagicMock()
    fake_resp.text = _RSS_XML
    fake_resp.raise_for_status.return_value = None

    with patch("services.news_service._news_session.get", return_value=fake_resp) as mock_get:
        resp = client.get("/api/stock/2330.TW/news?limit=2")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "2330.TW"
    assert body["query"] == "台積電"
    assert len(body["articles"]) == 2  # limit=2 生效（RSS 回 3 則）
    assert body["articles"][0]["title"] == "新聞標題一"
    assert body["articles"][0]["source"] == "來源A"
    assert body["articles"][0]["link"] == "https://example.com/a"
    assert "2026" in body["articles"][0]["published"]
    mock_get.assert_called_once()  # 網路只打一次


@patch("api.routes.stock.get_stock_overview")
def test_news_route_no_results_returns_empty_list_with_error_message(mock_overview):
    mock_overview.return_value = StockOverviewData(ticker="9999.TW", name="測試股")

    empty_rss = '<?xml version="1.0"?><rss><channel></channel></rss>'
    fake_resp = MagicMock()
    fake_resp.text = empty_rss
    fake_resp.raise_for_status.return_value = None

    with patch("services.news_service._news_session.get", return_value=fake_resp):
        resp = client.get("/api/stock/9999.TW/news")

    assert resp.status_code == 200
    body = resp.json()
    assert body["articles"] == []
    assert body["error"] != ""


# ── /api/stock/{ticker}/monthly-revenue ─────────────────────────────────────


@patch("api.routes.stock.get_monthly_revenue")
@patch("api.routes.stock.normalize_ticker", return_value="2330.TW")
def test_monthly_revenue_route_contract(mock_normalize, mock_get_rev):
    mock_get_rev.return_value = MonthlyRevenue(
        code="2330",
        yoy=0.30,
        label="115年6月",
        revenue=263711798,
        mom=0.055,
        yoy_acc=0.284,
    )

    resp = client.get("/api/stock/2330/monthly-revenue")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "2330.TW"
    assert body["label"] == "115年6月"
    assert body["revenue"] == 263711798
    assert body["yoy"] == pytest.approx(0.30)
    assert body["mom"] == pytest.approx(0.055)
    assert body["yoy_acc"] == pytest.approx(0.284)


@patch("api.routes.stock.get_monthly_revenue", return_value=None)
@patch("api.routes.stock.normalize_ticker", return_value="6488.TWO")
def test_monthly_revenue_route_404_for_otc(mock_normalize, mock_get_rev):
    resp = client.get("/api/stock/6488/monthly-revenue")
    assert resp.status_code == 404


@patch("api.routes.stock.get_monthly_revenue", return_value=None)
@patch("api.routes.stock.normalize_ticker", return_value="2330.TW")
def test_monthly_revenue_route_404_when_not_found(mock_normalize, mock_get_rev):
    resp = client.get("/api/stock/2330/monthly-revenue")
    assert resp.status_code == 404


# ── /api/stock/{ticker}/industry-pe ──────────────────────────────────────────


@patch("api.routes.stock.get_industry_pe")
@patch("api.routes.stock.normalize_ticker", return_value="2330.TW")
def test_industry_pe_route_contract(mock_normalize, mock_get_pe):
    mock_get_pe.return_value = IndustryPeResult(
        ticker="2330.TW",
        stock_pe=18.5,
        industry="半導體業（TWSE 細分類）",
        percentile=73.2,
        sample_size=42,
        median_pe=15.0,
    )

    resp = client.get("/api/stock/2330/industry-pe")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "2330.TW"
    assert body["stock_pe"] == pytest.approx(18.5)
    assert body["percentile"] == pytest.approx(73.2)
    assert body["sample_size"] == 42
    assert body["median_pe"] == pytest.approx(15.0)
    assert "細分類" in body["industry"]


@patch("api.routes.stock.get_industry_pe", return_value=None)
@patch("api.routes.stock.normalize_ticker", return_value="2330.TW")
def test_industry_pe_route_404_when_insufficient_sample(mock_normalize, mock_get_pe):
    resp = client.get("/api/stock/2330/industry-pe")
    assert resp.status_code == 404


@patch("api.routes.stock.get_industry_pe", return_value=None)
@patch("api.routes.stock.normalize_ticker", return_value="6488.TWO")
def test_industry_pe_route_404_for_otc(mock_normalize, mock_get_pe):
    resp = client.get("/api/stock/6488/industry-pe")
    assert resp.status_code == 404
