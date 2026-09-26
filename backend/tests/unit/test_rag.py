"""Unit tests for RAG retriever abstraction and mock search."""

import pytest
from app.rag.mock import MockRetriever


@pytest.mark.asyncio
async def test_mock_retriever():
    """Verify MockRetriever returns relevant chunks matching query parameters."""
    retriever = MockRetriever()
    result = await retriever.search(query="marble maintenance care", top_k=2)

    assert result.query == "marble maintenance care"
    assert len(result.chunks) <= 2
    assert result.chunks[0].score > 0.0
    assert "marble" in result.chunks[0].content.lower()
    assert "care_guide" in result.chunks[0].metadata.get("category", "")
