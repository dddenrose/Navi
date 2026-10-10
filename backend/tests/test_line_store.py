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


# ── in-flight lock ──────────────────────────────────────────────────────────


def _acquire(inflight_until) -> tuple[bool, MagicMock, MagicMock]:
    """Run try_acquire_inflight against a link doc holding ``inflight_until``.

    transactional() is unwrapped so the test exercises our read-then-write, not
    the Firestore client's retry machinery.
    """
    db, link_ref = _mock_db()
    link_ref.get.return_value.to_dict.return_value = {
        "uid": "uid-1",
        "inflight_until": inflight_until,
    }
    with (
        patch("services.line.store.get_db", return_value=db),
        patch("services.line.store.firestore_module.transactional", side_effect=lambda fn: fn),
    ):
        acquired = store.try_acquire_inflight("U1")
    transaction = db.transaction.return_value
    link_ref.get.assert_called_once_with(transaction=transaction)
    return acquired, link_ref, transaction


def test_acquire_when_nothing_in_flight():
    acquired, link_ref, transaction = _acquire(None)
    assert acquired is True
    ref, update = transaction.update.call_args.args
    assert ref is link_ref
    lease = update["inflight_until"] - datetime.now(UTC)
    assert timedelta(seconds=store.INFLIGHT_LEASE_SECONDS - 5) < lease
    assert lease <= timedelta(seconds=store.INFLIGHT_LEASE_SECONDS)


def test_acquire_after_lease_expired():
    acquired, _, transaction = _acquire(datetime.now(UTC) - timedelta(seconds=1))
    assert acquired is True
    transaction.update.assert_called_once()


def test_acquire_while_held_is_refused():
    acquired, _, transaction = _acquire(datetime.now(UTC) + timedelta(seconds=60))
    assert acquired is False
    transaction.update.assert_not_called()


def test_acquire_fails_open_on_firestore_error():
    with patch("services.line.store.get_db", side_effect=RuntimeError("firestore down")):
        assert store.try_acquire_inflight("U1") is True


def test_release_clears_the_lock():
    db, link_ref = _mock_db()
    with patch("services.line.store.get_db", return_value=db):
        store.release_inflight("U1")
    db.collection.assert_called_with("line_links")
    link_ref.update.assert_called_once_with({"inflight_until": None})


def test_release_never_raises():
    with patch("services.line.store.get_db", side_effect=RuntimeError("firestore down")):
        store.release_inflight("U1")


# ── create_link_if_absent ───────────────────────────────────────────────────


def test_create_link_when_absent():
    db, doc_ref = _mock_db()
    with patch("services.line.store.get_db", return_value=db):
        link = store.create_link_if_absent("U1", "line_U1")
    payload = doc_ref.create.call_args.args[0]
    assert payload["uid"] == "line_U1"
    assert payload["conversation_id"] is None
    assert link["uid"] == "line_U1"
    assert isinstance(link["linked_at"], datetime)
    doc_ref.set.assert_not_called()


def test_existing_link_is_kept_and_returned():
    db, doc_ref = _mock_db()
    doc_ref.create.side_effect = AlreadyExists("exists")
    doc_ref.get.return_value.to_dict.return_value = {"uid": "web-uid", "email": "me@example.com"}
    with patch("services.line.store.get_db", return_value=db):
        link = store.create_link_if_absent("U1", "line_U1")
    assert link == {"uid": "web-uid", "email": "me@example.com"}
    doc_ref.set.assert_not_called()
