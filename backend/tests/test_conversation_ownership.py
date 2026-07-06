"""對話擁有權檢查測試 — 防止 IDOR（拿他人 conversation_id 注入/續寫歷史）."""

from unittest.mock import MagicMock, patch

from services.conversation_service import load_history, save_history


def _mock_db_with_doc(doc_data: dict | None):
    """Build a mock Firestore db whose document get() returns doc_data."""
    doc = MagicMock()
    doc.exists = doc_data is not None
    doc.to_dict.return_value = doc_data
    doc_ref = MagicMock()
    doc_ref.get.return_value = doc
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    return db, doc_ref


OTHERS_CONV = {
    "user_id": "owner-uid",
    "messages": [
        {"role": "human", "content": "我的持股有哪些？"},
        {"role": "ai", "content": "你持有台積電 10 張。"},
    ],
}


class TestLoadHistoryOwnership:
    def test_owner_can_load(self):
        db, _ = _mock_db_with_doc(OTHERS_CONV)
        with patch("services.conversation_service.get_db", return_value=db):
            history = load_history("conv-1", user_id="owner-uid")
        assert len(history) == 2

    def test_non_owner_gets_empty(self):
        db, _ = _mock_db_with_doc(OTHERS_CONV)
        with patch("services.conversation_service.get_db", return_value=db):
            history = load_history("conv-1", user_id="attacker-uid")
        assert history == []

    def test_missing_doc_returns_empty(self):
        db, _ = _mock_db_with_doc(None)
        with patch("services.conversation_service.get_db", return_value=db):
            assert load_history("conv-x", user_id="anyone") == []


class TestSaveHistoryOwnership:
    def test_non_owner_save_is_skipped(self):
        db, doc_ref = _mock_db_with_doc(OTHERS_CONV)
        with patch("services.conversation_service.get_db", return_value=db):
            save_history("conv-1", "hi", "hello", user_id="attacker-uid")
        doc_ref.set.assert_not_called()

    def test_owner_save_writes(self):
        db, doc_ref = _mock_db_with_doc(OTHERS_CONV)
        with patch("services.conversation_service.get_db", return_value=db):
            save_history("conv-1", "hi", "hello", user_id="owner-uid")
        doc_ref.set.assert_called_once()
