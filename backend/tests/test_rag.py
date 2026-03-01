"""Tests for RAG service.

Requires valid GCP credentials and knowledge documents in Firestore.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and not os.getenv("GOOGLE_CLOUD_PROJECT"),
    reason="GCP credentials not configured",
)


@pytest.mark.asyncio
async def test_analyze_rsi_question():
    """Ask about RSI and expect a non-empty, knowledge-grounded response."""
    from services.rag_service import analyze

    chunks = []
    async for chunk in analyze("什麼是 RSI？何時該使用？"):
        chunks.append(chunk)

    full_response = "".join(chunks)
    assert len(full_response) > 50, "Response should be substantial"
    # Should reference RSI concepts from knowledge base
    assert "RSI" in full_response


@pytest.mark.asyncio
async def test_get_sources():
    """Knowledge search should return source metadata."""
    from services.rag_service import get_sources_from_search

    sources = get_sources_from_search("什麼是 RSI？")
    assert isinstance(sources, list)
    # If knowledge base is ingested, we should get results
    if sources:
        assert "source_file" in sources[0]
