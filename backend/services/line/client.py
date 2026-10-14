"""LINE Messaging API client — 簽章驗證、reply / push / loading 動畫、用量、profile 與圖片下載.

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
# 使用者傳的圖片等內容要從另一個網域下載
DATA_API_BASE = "https://api-data.line.me/v2/bot"
MAX_CONTENT_BYTES = 10 * 1024 * 1024  # LINE 圖片上限 10 MB
TIMEOUT_SECONDS = 10
LOADING_SECONDS = 60  # LINE 允許 5–60 秒
PUSH_USAGE_WARN_RATIO = 0.8  # 當月 push 用量達方案上限的這個比例時，log 升為 WARNING


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
        logger.info("[LINE dry-run] POST %s %s", path, json.dumps(payload, ensure_ascii=False))
        return None
    return requests.post(
        f"{API_BASE}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_SECONDS,
    )


def _get(path: str) -> dict | None:
    """GET a LINE API resource as JSON; None in dry-run. Raises on HTTP errors."""
    token = settings.line_channel_access_token
    if not token:
        return None
    response = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


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


async def log_push_usage() -> None:
    """Log this month's push usage against the plan's limit. Never raises.

    push 計入方案每月則數（輕用量 200 則），用完後 push 會失敗、那則回覆就送不到。
    每次 push 後記一筆，要不要處理冷啟動造成的 push 就看這個數字。
    """
    try:
        quota, consumption = await asyncio.gather(
            asyncio.to_thread(_get, "/message/quota"),
            asyncio.to_thread(_get, "/message/quota/consumption"),
        )
        if quota is None or consumption is None:
            return
        used = int(consumption.get("totalUsage", 0))
        limit = quota.get("value") if quota.get("type") == "limited" else None
        near_limit = limit is not None and used >= limit * PUSH_USAGE_WARN_RATIO
        logger.log(
            logging.WARNING if near_limit else logging.INFO,
            "LINE push usage this month: %d/%s",
            used,
            limit if limit is not None else "unlimited",
        )
    except Exception:
        logger.warning("LINE push usage lookup failed", exc_info=True)


def _get_content(message_id: str) -> tuple[bytes, str] | None:
    token = settings.line_channel_access_token
    if not token:
        logger.info("[LINE dry-run] GET content of message %s", message_id)
        return None
    response = requests.get(
        f"{DATA_API_BASE}/message/{message_id}/content",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_SECONDS,
    )
    # 202 = LINE 還在處理（影片才常見）；當成拿不到
    if response.status_code != 200:
        logger.warning("LINE content %s returned %s", message_id, response.status_code)
        return None
    if len(response.content) > MAX_CONTENT_BYTES:
        logger.warning("LINE content %s too large: %d bytes", message_id, len(response.content))
        return None
    mime_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    return response.content, mime_type


async def get_message_content(message_id: str) -> tuple[bytes, str] | None:
    """Download what a user sent (e.g. an image) as (bytes, mime type). Never raises.

    回 None 表示拿不到：dry-run、LINE 回非 200、超過大小上限或連線失敗。
    """
    try:
        return await asyncio.to_thread(_get_content, message_id)
    except Exception:
        logger.warning("LINE content download failed for %s", message_id, exc_info=True)
        return None


def get_display_name(user_id: str) -> str:
    """Return a LINE user's display name, or "" when unavailable. Never raises.

    只查得到已加 bot 好友的人；dry-run 或查詢失敗時回空字串。
    """
    try:
        profile = _get(f"/profile/{user_id}")
    except Exception:
        logger.warning("LINE profile lookup failed for %s", user_id, exc_info=True)
        return ""
    return (profile or {}).get("displayName", "")


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
