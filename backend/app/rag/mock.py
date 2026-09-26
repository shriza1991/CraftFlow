"""Mock Retriever for offline development and testing."""

from typing import Any

from app.rag.base import RetrievalChunk, RetrievalResult, Retriever


class MockRetriever(Retriever):
    """Deterministic retriever returning test knowledge snippets."""

    DEFAULT_KNOWLEDGE = [
        RetrievalChunk(
            id="chunk_1",
            document_id="doc_material_care",
            content="Ages Art marble bathtubs are sculpted from solid blocks of Italian Carrara and Spanish Marquina marble. Clean only with pH-neutral stone cleaner.",
            score=0.95,
            metadata={"category": "care_guide"},
        ),
        RetrievalChunk(
            id="chunk_2",
            document_id="doc_lead_times",
            content="Standard production lead time for custom sculpted marble bathtubs is 8 to 12 weeks, followed by white-glove international shipping.",
            score=0.88,
            metadata={"category": "shipping_policy"},
        ),
    ]

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> RetrievalResult:
        chunks = self.DEFAULT_KNOWLEDGE[:top_k]
        return RetrievalResult(
            query=query,
            chunks=chunks,
            total_found=len(chunks),
        )
