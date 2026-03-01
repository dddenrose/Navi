"""Tests for embedding service.

Requires valid GCP credentials. Skip if not configured.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and not os.getenv("GOOGLE_CLOUD_PROJECT"),
    reason="GCP credentials not configured",
)


def test_get_embedding_returns_768_dims():
    """text-embedding-004 should return a 768-dimensional vector."""
    from services.embedding_service import get_embedding

    vector = get_embedding("什麼是 RSI 指標？", task_type="RETRIEVAL_QUERY")
    assert isinstance(vector, list)
    assert len(vector) == 768
    assert all(isinstance(v, float) for v in vector)


def test_store_and_search():
    """End-to-end: store a document, then find it via vector search."""
    from services.embedding_service import search_similar, store_document
    from services.firestore_client import get_db
    from config import settings

    # Store a test document
    test_content = "RSI（相對強弱指標）是一種動量振盪指標，用於衡量價格變動的速度和幅度。"
    test_metadata = {
        "source_file": "test_rsi.md",
        "category": "technical_analysis",
        "title": "RSI 測試文件",
        "chunk_index": 0,
    }

    doc_id = store_document(test_content, test_metadata)
    assert doc_id  # should be a non-empty string

    try:
        # Search for it
        results = search_similar("什麼是 RSI？", top_k=3)
        assert len(results) > 0

        # At least one result should contain our content
        found = any("RSI" in r["content"] for r in results)
        assert found, f"Expected to find RSI document, got: {results}"
    finally:
        # Cleanup
        db = get_db()
        db.collection(settings.firestore_collection_knowledge).document(doc_id).delete()
