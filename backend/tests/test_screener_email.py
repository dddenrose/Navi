"""Tests for screener email sender — SendGrid mocked, no real email sent."""

from unittest.mock import MagicMock, patch

from services.screener.email_sender import (
    make_unsubscribe_token,
    render_email_html,
    send_report_email,
    verify_unsubscribe_token,
)


# ── HMAC unsubscribe token ──────────────────────────────────────────────────


def test_unsubscribe_token_roundtrip():
    user_id = "user-abc-123"
    token = make_unsubscribe_token(user_id)
    assert verify_unsubscribe_token(token) == user_id


def test_unsubscribe_token_rejects_tampering():
    token = make_unsubscribe_token("user-abc")
    assert verify_unsubscribe_token(token + "x") is None
    assert verify_unsubscribe_token("evil.deadbeef") is None
    assert verify_unsubscribe_token("") is None


# ── HTML render ─────────────────────────────────────────────────────────────


def test_render_email_html_includes_picks_and_unsubscribe():
    report = {"report_id": "20260501-weekly-momentum", "final_count": 2, "industries_covered": ["半導體"]}
    picks_by_industry = {
        "半導體": [
            {
                "ticker": "2330.TW",
                "name": "台積電",
                "rank_in_industry": 1,
                "confidence": 88,
                "upside_pct": 14.8,
                "target_price": {"low": 700, "mid": 750, "high": 820},
                "snapshot": {"price": 650},
                "thesis": "AI 驅動先進製程需求強勁。",
                "risks": ["地緣政治", "匯率"],
            }
        ]
    }
    html = render_email_html(
        report,
        picks_by_industry,
        user_id="uid-1",
        profile="momentum",
        public_base_url="https://example.com",
    )
    assert "台積電" in html
    assert "2330" in html
    assert "信心 88" in html
    assert "https://example.com/api/screener/unsubscribe?token=" in html
    assert "https://example.com/screener" in html


# ── send_report_email：SendGrid 模擬 ──────────────────────────────────────


@patch("services.screener.email_sender.list_active_subscribers")
@patch("services.screener.email_sender._load_report")
def test_send_report_email_dry_run_when_no_api_key(mock_load, mock_list):
    mock_load.return_value = (
        {"report_id": "r1", "final_count": 1, "industries_covered": []},
        {"半導體": [{"ticker": "2330.TW", "name": "TSMC", "rank_in_industry": 1,
                    "confidence": 80, "upside_pct": 10, "target_price": {"mid": 700},
                    "snapshot": {"price": 650}, "thesis": "ok", "risks": []}]},
    )
    mock_list.return_value = [{"user_id": "u1", "email": "u1@test.com", "enabled": True}]

    with patch("services.screener.email_sender.settings") as mock_settings:
        mock_settings.sendgrid_api_key = ""
        mock_settings.email_from_address = "from@test.com"
        mock_settings.email_from_name = "Navi"
        mock_settings.screener_public_base_url = "https://example.com"
        mock_settings.screener_unsubscribe_secret = "test-secret"
        result = send_report_email("r1", profile="momentum", frequency="weekly")
    assert result.dry_run is True
    assert result.skipped == 1
    assert result.sent == 0


@patch("services.screener.email_sender.list_active_subscribers")
@patch("services.screener.email_sender._load_report")
def test_send_report_email_uses_sendgrid_when_key_present(mock_load, mock_list):
    mock_load.return_value = (
        {"report_id": "r1", "final_count": 1, "industries_covered": []},
        {"半導體": [{"ticker": "2330.TW", "name": "TSMC", "rank_in_industry": 1,
                    "confidence": 80, "upside_pct": 10, "target_price": {"mid": 700},
                    "snapshot": {"price": 650}, "thesis": "ok", "risks": []}]},
    )
    mock_list.return_value = [{"user_id": "u1", "email": "u1@test.com", "enabled": True}]

    fake_resp = MagicMock(status_code=202, body=b"")
    fake_client = MagicMock()
    fake_client.send.return_value = fake_resp

    with patch("services.screener.email_sender.settings") as mock_settings, \
         patch("sendgrid.SendGridAPIClient", return_value=fake_client):
        mock_settings.sendgrid_api_key = "SG.fake"
        mock_settings.email_from_address = "from@test.com"
        mock_settings.email_from_name = "Navi"
        mock_settings.screener_public_base_url = "https://example.com"
        mock_settings.screener_unsubscribe_secret = "test-secret"
        result = send_report_email("r1", profile="momentum", frequency="weekly")
    assert result.sent == 1
    assert result.failed == 0
    fake_client.send.assert_called_once()
