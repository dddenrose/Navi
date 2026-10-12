"""對話保存期限與整批刪除 — LINE-only 帳號的對話會到期，網頁帳號的不會."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from services.conversation_service import delete_all_conversations, save_history
from services.line import LINE_ONLY_RETENTION_DAYS

LINE_ONLY_UID = "line_U" + "a" * 32


def _saved_fields(user_id: str) -> dict:
    doc = MagicMock()
    doc.exists = False
    db = MagicMock()
    doc_ref = db.collection.return_value.document.return_value
    doc_ref.get.return_value = doc
    with patch("services.conversation_service.get_db", return_value=db):
        save_history("conv-1", "hi", "hello", user_id=user_id)
    return doc_ref.set.call_args.args[0]


def test_line_only_conversation_expires_after_retention_period():
    expires_at = _saved_fields(LINE_ONLY_UID)["expires_at"]
    expected = datetime.now(UTC) + timedelta(days=LINE_ONLY_RETENTION_DAYS)
    assert abs(expires_at - expected) < timedelta(minutes=1)


def test_web_account_conversation_never_expires():
    assert "expires_at" not in _saved_fields("web-uid")


def _db_with_conversations(count: int) -> MagicMock:
    db = MagicMock()
    docs = [MagicMock(reference=f"ref-{i}") for i in range(count)]
    query = db.collection.return_value.where.return_value
    query.select.return_value.stream.return_value = docs
    return db


def test_delete_all_conversations_only_queries_the_users_own():
    db = _db_with_conversations(2)
    with patch("services.conversation_service.get_db", return_value=db):
        assert delete_all_conversations(LINE_ONLY_UID) == 2
    db.collection.return_value.where.assert_called_once_with("user_id", "==", LINE_ONLY_UID)
    batch = db.batch.return_value
    assert [c.args[0] for c in batch.delete.call_args_list] == ["ref-0", "ref-1"]
    batch.commit.assert_called_once()


def test_delete_all_conversations_commits_in_batches_of_500():
    db = _db_with_conversations(501)
    with patch("services.conversation_service.get_db", return_value=db):
        assert delete_all_conversations(LINE_ONLY_UID) == 501
    assert db.batch.return_value.commit.call_count == 2


def test_delete_all_conversations_refuses_an_empty_uid():
    with pytest.raises(ValueError):
        delete_all_conversations("")
