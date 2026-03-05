"""Conversation Service — Multi-turn memory backed by Firestore."""

import logging
import uuid
from datetime import datetime, timezone

from google.cloud import firestore as firestore_module
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from config import settings
from services.firestore_client import get_db

logger = logging.getLogger(__name__)

COLLECTION = "conversations"
MAX_TURNS = 20  # Keep last N turns to avoid context overflow


def new_conversation_id() -> str:
    """Generate a new unique conversation ID."""
    return uuid.uuid4().hex[:16]


def _msg_to_dict(msg: BaseMessage) -> dict:
    return {
        "role": "human" if isinstance(msg, HumanMessage) else "ai",
        "content": msg.content,
    }


def _dict_to_msg(d: dict) -> BaseMessage:
    if d["role"] == "human":
        return HumanMessage(content=d["content"])
    return AIMessage(content=d["content"])


# ── Firestore persistence ───────────────────────────────────────────────────


def load_history(conversation_id: str) -> list[BaseMessage]:
    """Load conversation history from Firestore.

    Returns:
        List of LangChain message objects (HumanMessage / AIMessage).
    """
    db = get_db()
    doc_ref = db.collection(COLLECTION).document(conversation_id)
    doc = doc_ref.get()

    if not doc.exists:
        return []

    data = doc.to_dict() or {}
    messages_data = data.get("messages", [])
    return [_dict_to_msg(m) for m in messages_data[-MAX_TURNS * 2 :]]


def save_history(
    conversation_id: str,
    user_message: str,
    assistant_message: str,
    user_id: str = "",
) -> None:
    """Append a turn (user + assistant) to the conversation in Firestore."""
    db = get_db()
    doc_ref = db.collection(COLLECTION).document(conversation_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict() or {}
        messages = data.get("messages", [])
    else:
        messages = []

    messages.append({"role": "human", "content": user_message})
    messages.append({"role": "ai", "content": assistant_message})

    # Trim old messages
    if len(messages) > MAX_TURNS * 2:
        messages = messages[-(MAX_TURNS * 2) :]

    update_data: dict = {
        "messages": messages,
        "updated_at": firestore_module.SERVER_TIMESTAMP,
        "turn_count": len(messages) // 2,
    }

    # Set user_id and title on first save (conversation creation)
    if not doc.exists:
        update_data["user_id"] = user_id
        update_data["title"] = user_message[:60]
        update_data["created_at"] = firestore_module.SERVER_TIMESTAMP

    doc_ref.set(update_data, merge=True)


def delete_conversation(conversation_id: str, user_id: str = "") -> bool:
    """Delete a conversation from Firestore (with ownership check)."""
    db = get_db()
    doc_ref = db.collection(COLLECTION).document(conversation_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False
    # Verify ownership
    if user_id:
        doc_data = doc.to_dict() or {}
        if doc_data.get("user_id", "") != user_id:
            return False
    doc_ref.delete()
    return True


def list_conversations(user_id: str, limit: int = 20) -> list[dict]:
    """List recent conversations for a specific user."""
    db = get_db()
    query = db.collection(COLLECTION).where("user_id", "==", user_id)
    docs = (
        query
        .order_by("updated_at", direction=firestore_module.Query.DESCENDING)
        .limit(limit)
        .get()
    )
    return [
        {
            "conversation_id": doc.id,
            "title": (doc.to_dict() or {}).get("title", "對話記錄"),
            "message_count": (doc.to_dict() or {}).get("turn_count", 0),
            "created_at": str((doc.to_dict() or {}).get("created_at", "")),
            "updated_at": str((doc.to_dict() or {}).get("updated_at", "")),
        }
        for doc in docs
    ]
