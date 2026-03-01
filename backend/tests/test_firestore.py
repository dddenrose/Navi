"""Tests for Firestore connection.

Requires valid GCP credentials. Skip if not configured.
"""

import os
import uuid

import pytest

# Skip entire module if no credentials configured
pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and not os.getenv("GOOGLE_CLOUD_PROJECT"),
    reason="GCP credentials not configured",
)


def test_firestore_write_read_delete():
    """Test basic Firestore CRUD: write → read → delete."""
    from services.firestore_client import get_db

    db = get_db()
    collection = "_test_connection"
    doc_id = f"test-{uuid.uuid4().hex[:8]}"

    # Write
    doc_ref = db.collection(collection).document(doc_id)
    doc_ref.set({"message": "hello from navi", "test": True})

    # Read
    doc = doc_ref.get()
    assert doc.exists
    assert doc.to_dict()["message"] == "hello from navi"

    # Delete
    doc_ref.delete()
    doc = doc_ref.get()
    assert not doc.exists
