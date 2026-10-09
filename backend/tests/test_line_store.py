"""Tests for LINE Firestore access — event dedup, links, conversation continuity."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from google.api_core.exceptions import AlreadyExists

from services.line import store


def _mock_db():
    doc_ref = MagicMock()
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    return db, doc_ref


# ── claim_event ─────────────────────────────────────────────────────────────


def test_claim_event_first_time():
    db, doc_ref = _mock_db()
    with patch("services.line.store.get_db", return_value=db):
        assert store.claim_event("evt-1") is True
    db.collection.assert_called_with("line_events")
    payload = doc_ref.create.call_args.args[0]
    assert payload["expires_at"] - payload["claimed_at"] == timedelta(days=store.EVENT_TTL_DAYS)


def test_claim_event_duplicate_is_rejected():
    db, doc_ref = _mock_db()
    doc_ref.create.side_effect = AlreadyExists("exists")
    with patch("services.line.store.get_db", return_value=db):
        assert store.claim_event("evt-1") is False


def test_claim_event_fails_open_on_firestore_error():
    with patch("services.line.store.get_db", side_effect=RuntimeError("firestore down")):
        assert store.claim_event("evt-1") is True


# ── links ───────────────────────────────────────────────────────────────────


def test_get_link_missing_returns_none():
    db, doc_ref = _mock_db()
    doc_ref.get.return_value.exists = False
    with patch("services.line.store.get_db", return_value=db):
        assert store.get_link("U1") is None


def test_set_link_resets_conversation():
    db, doc_ref = _mock_db()
    with patch("services.line.store.get_db", return_value=db):
        store.set_link("U1", "uid-1", "me@example.com")
    payload = doc_ref.set.call_args.args[0]
    assert payload["uid"] == "uid-1"
    assert payload["email"] == "me@example.com"
    assert payload["conversation_id"] is None
    assert payload["last_message_at"] is None


# ── resolve_conversation ────────────────────────────────────────────────────


def _resolve(link: dict, **kwargs) -> tuple[str, dict]:
    db, doc_ref = _mock_db()
    with patch("services.line.store.get_db", return_value=db):
        conversation_id = store.resolve_conversation("U1", link, **kwargs)
    return conversation_id, doc_ref.update.call_args.args[0]


def test_recent_conversation_is_continued():
    recent = datetime.now(UTC) - timedelta(minutes=5)
    link = {"conversation_id": "conv-1", "last_message_at": recent}
    conversation_id, update = _resolve(link)
    assert conversation_id == "conv-1"
    assert update["conversation_id"] == "conv-1"
    assert datetime.now(UTC) - update["last_message_at"] < timedelta(seconds=5)


def test_idle_conversation_rolls_over():
    idle = timedelta(hours=store.SESSION_IDLE_HOURS, minutes=1)
    link = {"conversation_id": "conv-1", "last_message_at": datetime.now(UTC) - idle}
    conversation_id, update = _resolve(link)
    assert conversation_id != "conv-1"
    assert update["conversation_id"] == conversation_id


def test_first_message_starts_a_conversation():
    link = {"uid": "uid-1", "conversation_id": None, "last_message_at": None}
    conversation_id, _ = _resolve(link)
    assert conversation_id


def test_force_new_starts_a_conversation():
    link = {"conversation_id": "conv-1", "last_message_at": datetime.now(UTC)}
    conversation_id, _ = _resolve(link, force_new=True)
    assert conversation_id != "conv-1"
