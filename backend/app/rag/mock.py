"""Injectable mock retriever for offline development and testing."""

from typing import Any

from app.rag.base import RetrievalChunk, RetrievalResult, Retriever


class MockRetriever(Retriever):
    """Return explicitly provided test chunks; empty unless a caller supplies data."""

    def __init__(self, chunks: list[RetrievalChunk] | None = None):
        self.chunks = list(chunks or [])

    async def search(
        self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None
    ) -> RetrievalResult:
        chunks = self.chunks
        if filters:
            chunks = [
                chunk
                for chunk in chunks
                if all(chunk.metadata.get(k) == v for k, v in filters.items())
            ]
        return RetrievalResult(query=query, chunks=chunks[:top_k], total_found=len(chunks))
