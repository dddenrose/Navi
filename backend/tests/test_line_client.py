"""Tests for the LINE Messaging API client — signature + send behaviour (no network)."""

import base64
import hashlib
import hmac
import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from services.line import client

SECRET = "test-secret"
BODY = b'{"events":[]}'


def _sign(body: bytes, secret: str = SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


# ── verify_signature ────────────────────────────────────────────────────────


def test_valid_signature_accepted():
    assert client.verify_signature(BODY, _sign(BODY), SECRET) is True


@pytest.mark.parametrize(
    "signature",
    [None, "", "not-the-signature", _sign(b"another body"), _sign(BODY, "wrong-secret"), "簽章"],
)
def test_invalid_signature_rejected(signature):
    assert client.verify_signature(BODY, signature, SECRET) is False


def test_empty_channel_secret_rejects_everything():
    assert client.verify_signature(BODY, _sign(BODY, ""), "") is False


# ── reply / push / start_loading ────────────────────────────────────────────


def _response(status_code: int) -> MagicMock:
    response = MagicMock(status_code=status_code, text="{}")
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(str(status_code))
    return response


@patch("services.line.client.requests.post")
@patch("services.line.client.settings")
async def test_reply_sends_text_messages(mock_settings, mock_post):
    mock_settings.line_channel_access_token = "token-abc"
    mock_post.return_value = _response(200)

    assert await client.reply("reply-token", ["第一則", "第二則"]) is True

    url = mock_post.call_args.args[0]
    kwargs = mock_post.call_args.kwargs
    assert url == "https://api.line.me/v2/bot/message/reply"
    assert kwargs["headers"] == {"Authorization": "Bearer token-abc"}
    assert kwargs["json"] == {
        "replyToken": "reply-token",
        "messages": [{"type": "text", "text": "第一則"}, {"type": "text", "text": "第二則"}],
    }


@patch("services.line.client.requests.post")
@patch("services.line.client.settings")
async def test_reply_returns_false_on_rejected_token(mock_settings, mock_post):
    mock_settings.line_channel_access_token = "token-abc"
    mock_post.return_value = _response(400)
    assert await client.reply("expired-token", ["hi"]) is False


@patch("services.line.client.requests.post")
@patch("services.line.client.settings")
async def test_reply_raises_on_other_errors(mock_settings, mock_post):
    mock_settings.line_channel_access_token = "token-abc"
    mock_post.return_value = _response(500)
    with pytest.raises(requests.HTTPError):
        await client.reply("reply-token", ["hi"])


@patch("services.line.client.requests.post")
@patch("services.line.client.settings")
async def test_dry_run_without_access_token_sends_nothing(mock_settings, mock_post):
    mock_settings.line_channel_access_token = ""

    assert await client.reply("reply-token", ["hi"]) is True
    await client.push("U123", ["hi"])
    await client.start_loading("U123")

    mock_post.assert_not_called()


@patch("services.line.client.requests.post")
@patch("services.line.client.settings")
async def test_start_loading_never_raises(mock_settings, mock_post):
    mock_settings.line_channel_access_token = "token-abc"
    mock_post.side_effect = requests.ConnectionError("boom")
    await client.start_loading("U123")


# ── log_push_usage ──────────────────────────────────────────────────────────


def _json_response(payload: dict, status_code: int = 200) -> MagicMock:
    response = _response(status_code)
    response.json.return_value = payload
    return response


def _quota_api(quota: dict, consumption: dict):
    def _get(url, **kwargs):
        if url.endswith("/message/quota"):
            return _json_response(quota)
        if url.endswith("/message/quota/consumption"):
            return _json_response(consumption)
        raise AssertionError(f"unexpected GET {url}")

    return _get


def _usage_record(caplog) -> logging.LogRecord:
    return next(r for r in caplog.records if "LINE push usage this month" in r.getMessage())


@pytest.mark.parametrize(
    ("quota", "used", "expected_text", "expected_level"),
    [
        ({"type": "limited", "value": 200}, 12, "12/200", logging.INFO),
        ({"type": "limited", "value": 200}, 160, "160/200", logging.WARNING),
        ({"type": "none"}, 5, "5/unlimited", logging.INFO),
    ],
)
@patch("services.line.client.requests.get")
@patch("services.line.client.settings")
async def test_push_usage_is_logged(
    mock_settings, mock_get, caplog, quota, used, expected_text, expected_level
):
    mock_settings.line_channel_access_token = "token-abc"
    mock_get.side_effect = _quota_api(quota, {"totalUsage": used})

    with caplog.at_level(logging.INFO, logger="services.line.client"):
        await client.log_push_usage()

    record = _usage_record(caplog)
    assert expected_text in record.getMessage()
    assert record.levelno == expected_level
    assert mock_get.call_args.kwargs["headers"] == {"Authorization": "Bearer token-abc"}


@patch("services.line.client.requests.get")
@patch("services.line.client.settings")
async def test_push_usage_lookup_never_raises(mock_settings, mock_get):
    mock_settings.line_channel_access_token = "token-abc"
    mock_get.side_effect = requests.ConnectionError("boom")
    await client.log_push_usage()


@patch("services.line.client.requests.get")
@patch("services.line.client.settings")
async def test_push_usage_skipped_in_dry_run(mock_settings, mock_get):
    mock_settings.line_channel_access_token = ""
    await client.log_push_usage()
    mock_get.assert_not_called()


# ── get_display_name ────────────────────────────────────────────────────────


@patch("services.line.client.requests.get")
@patch("services.line.client.settings")
def test_display_name_from_profile(mock_settings, mock_get):
    mock_settings.line_channel_access_token = "token-abc"
    mock_get.return_value = _json_response({"userId": "U123", "displayName": "阿明"})

    assert client.get_display_name("U123") == "阿明"
    assert mock_get.call_args.args[0] == "https://api.line.me/v2/bot/profile/U123"


@patch("services.line.client.requests.get")
@patch("services.line.client.settings")
def test_display_name_empty_when_profile_unavailable(mock_settings, mock_get):
    mock_settings.line_channel_access_token = "token-abc"
    mock_get.return_value = _json_response({"message": "Not found"}, status_code=404)
    assert client.get_display_name("U123") == ""


@patch("services.line.client.requests.get")
@patch("services.line.client.settings")
def test_display_name_empty_in_dry_run(mock_settings, mock_get):
    mock_settings.line_channel_access_token = ""
    assert client.get_display_name("U123") == ""
    mock_get.assert_not_called()
