"""LINE 相關的 Firestore 存取 — 事件去重、帳號綁定、對話延續、每人一題的鎖."""

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
# 鎖的租約：不短於 Cloud Tasks 的 dispatch deadline（300 秒），處理中不會提早失效；
# 行程中途當掉、沒走到 release 時，最多卡這麼久就自動解開。
INFLIGHT_LEASE_SECONDS = 300


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


def _new_link(uid: str, email: str) -> dict:
    return {
        "uid": uid,
        "email": email,
        "linked_at": firestore_module.SERVER_TIMESTAMP,
        # 換綁到別的 uid 時，舊對話不屬於新 uid，必須重開
        "conversation_id": None,
        "last_message_at": None,
    }


def set_link(line_user_id: str, uid: str, email: str = "") -> None:
    """Link a LINE user to a Firebase uid (overwrites any previous link)."""
    get_db().collection(LINKS_COLLECTION).document(line_user_id).set(_new_link(uid, email))


def create_link_if_absent(line_user_id: str, uid: str, email: str = "") -> dict:
    """Link a LINE user unless they already are; return the link now in place.

    用 create() 而不是 set()：同一人的兩個事件同時建帳號，或剛好有人用腳本綁到網頁帳號時，
    不會互相覆蓋。
    """
    link_ref = get_db().collection(LINKS_COLLECTION).document(line_user_id)
    link = _new_link(uid, email)
    try:
        link_ref.create(link)
    except Conflict:
        return link_ref.get().to_dict() or {}
    return {**link, "linked_at": datetime.now(UTC)}


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


def _claim_inflight(transaction, link_ref) -> bool:
    snapshot = link_ref.get(transaction=transaction)
    inflight_until = (snapshot.to_dict() or {}).get("inflight_until")
    now = datetime.now(UTC)
    if isinstance(inflight_until, datetime) and inflight_until > now:
        return False
    transaction.update(
        link_ref, {"inflight_until": now + timedelta(seconds=INFLIGHT_LEASE_SECONDS)}
    )
    return True


def try_acquire_inflight(line_user_id: str) -> bool:
    """Mark that this LINE user has a question in progress; False if one already is.

    對話記錄是讀後寫、沒有 transaction：同一人兩題同時跑，後寫的會蓋掉先寫的。
    佔位記在 line_links 文件的 inflight_until，在 transaction 內讀後寫，
    兩題同時搶時只有一題拿得到。Firestore 出錯時 fail-open（寧可冒互蓋的風險，
    也不要吞掉問題）。
    """
    try:
        db = get_db()
        link_ref = db.collection(LINKS_COLLECTION).document(line_user_id)
        return firestore_module.transactional(_claim_inflight)(db.transaction(), link_ref)
    except Exception:
        logger.exception("Failed to acquire LINE in-flight lock for %s, fail-open", line_user_id)
        return True


def release_inflight(line_user_id: str) -> None:
    """Clear the in-progress mark. Never raises: the lease expires on its own anyway."""
    try:
        get_db().collection(LINKS_COLLECTION).document(line_user_id).update(
            {"inflight_until": None}
        )
    except Exception:
        logger.warning("Failed to release LINE in-flight lock for %s", line_user_id, exc_info=True)
