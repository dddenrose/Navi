"""LINE 相關的 Firestore 存取 — 事件去重、帳號綁定、對話延續."""

import logging
from datetime import UTC, datetime, timedelta

from google.api_core.exceptions import Conflict
from google.cloud import firestore as firestore_module

from services.conversation_service import new_conversation_id
from services.firestore_client import get_db

logger = logging.getLogger(__name__)

LINKS_COLLECTION = "line_links"
EVENTS_COLLECTION = "line_events"
EVENT_TTL_DAYS = 7
SESSION_IDLE_HOURS = 6  # 閒置超過這個時間就開新對話


def claim_event(event_id: str) -> bool:
    """Mark a webhook event as being handled; False if it was already claimed.

    LINE 重送與 Cloud Tasks 重試都會帶同一個 webhookEventId，靠這裡擋掉重複處理。
    Firestore 出錯時 fail-open（寧可重複回答，也不要吞掉訊息）。
    """
    now = datetime.now(UTC)
    try:
        get_db().collection(EVENTS_COLLECTION).document(event_id).create(
            {"claimed_at": now, "expires_at": now + timedelta(days=EVENT_TTL_DAYS)}
        )
        return True
    except Conflict:
        return False
    except Exception:
        logger.exception("Failed to claim LINE event %s, fail-open", event_id)
        return True


def get_link(line_user_id: str) -> dict | None:
    """Return the link doc for a LINE user, or None if not linked."""
    snapshot = get_db().collection(LINKS_COLLECTION).document(line_user_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def set_link(line_user_id: str, uid: str, email: str = "") -> None:
    """Link a LINE user to a Firebase uid (overwrites any previous link)."""
    get_db().collection(LINKS_COLLECTION).document(line_user_id).set(
        {
            "uid": uid,
            "email": email,
            "linked_at": firestore_module.SERVER_TIMESTAMP,
            # 換綁到別的 uid 時，舊對話不屬於新 uid，必須重開
            "conversation_id": None,
            "last_message_at": None,
        }
    )


def resolve_conversation(line_user_id: str, link: dict, *, force_new: bool = False) -> str:
    """Return the conversation id for this message and record the activity.

    LINE 沒有「新對話」按鈕：沿用上一個對話，閒置過久或 force_new 時才換新的。
    """
    now = datetime.now(UTC)
    conversation_id = link.get("conversation_id")
    last_message_at = link.get("last_message_at")
    idle_too_long = not isinstance(last_message_at, datetime) or (
        now - last_message_at > timedelta(hours=SESSION_IDLE_HOURS)
    )
    if force_new or not conversation_id or idle_too_long:
        conversation_id = new_conversation_id()

    get_db().collection(LINKS_COLLECTION).document(line_user_id).update(
        {"conversation_id": conversation_id, "last_message_at": now}
    )
    return conversation_id
