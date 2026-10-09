"""Tests for the LINE Messaging API client — signature + send behaviour (no network)."""

import base64
import hashlib
import hmac
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
