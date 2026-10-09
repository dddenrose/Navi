"""LINE Messaging API client — 簽章驗證與 reply / push / loading 動畫.

未設定 LINE_CHANNEL_ACCESS_TOKEN 時走 dry-run：只 log 要送的內容，不呼叫 LINE。
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging

import requests

from config import settings

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Line-Signature"
API_BASE = "https://api.line.me/v2/bot"
TIMEOUT_SECONDS = 10
LOADING_SECONDS = 60  # LINE 允許 5–60 秒


def verify_signature(body: bytes, signature: str | None, channel_secret: str) -> bool:
    """Check X-Line-Signature = base64(HMAC-SHA256(channel secret, raw body))."""
    if not signature or not channel_secret:
        return False
    expected = base64.b64encode(
        hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    )
    # 以 bytes 比對：compare_digest 對非 ASCII 的 str 會丟 TypeError
    return hmac.compare_digest(expected, signature.encode("utf-8"))


def _post(path: str, payload: dict) -> requests.Response | None:
    token = settings.line_channel_access_token
    if not token:
        logger.info(
            "[LINE dry-run] POST %s %s", path, json.dumps(payload, ensure_ascii=False)
        )
        return None
    return requests.post(
        f"{API_BASE}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_SECONDS,
    )


def _text_messages(texts: list[str]) -> list[dict]:
    return [{"type": "text", "text": text} for text in texts]


async def reply(reply_token: str, texts: list[str]) -> bool:
    """Send a reply message (free of charge).

    Returns False when LINE rejects the request with 400 — in practice an
    expired or already-used reply token — so the caller can fall back to push.
    """
    response = await asyncio.to_thread(
        _post,
        "/message/reply",
        {"replyToken": reply_token, "messages": _text_messages(texts)},
    )
    if response is None:
        return True
    if response.status_code == 400:
        logger.info("LINE reply rejected: %s", response.text[:200])
        return False
    response.raise_for_status()
    return True


async def push(user_id: str, texts: list[str]) -> None:
    """Send a push message (counts against the monthly message quota)."""
    response = await asyncio.to_thread(
        _post, "/message/push", {"to": user_id, "messages": _text_messages(texts)}
    )
    if response is not None:
        response.raise_for_status()


async def start_loading(user_id: str, seconds: int = LOADING_SECONDS) -> None:
    """Show the loading animation in a one-on-one chat. Never raises."""
    try:
        response = await asyncio.to_thread(
            _post, "/chat/loading/start", {"chatId": user_id, "loadingSeconds": seconds}
        )
        if response is not None:
            response.raise_for_status()
    except Exception:
        logger.warning("LINE loading animation failed", exc_info=True)
