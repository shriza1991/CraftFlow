"""RAG Retriever abstract base interface and contracts."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class RetrievalChunk(BaseModel):
    """Individual knowledge chunk retrieved from vector/hybrid index."""

    id: str = Field(..., description="Unique identifier of chunk")
    document_id: str = Field(..., description="Parent document identifier")
    content: str = Field(..., description="Text content of the retrieved snippet")
    score: float = Field(..., description="Relevance or cosine similarity score")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata tags, e.g. section, tags"
    )


class RetrievalResult(BaseModel):
    """Aggregated search result returned by retriever."""

    query: str
    chunks: list[RetrievalChunk]
    total_found: int


class Retriever(ABC):
    """Abstract interface for knowledge retrieval engines (pgvector, hybrid, mock)."""

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> RetrievalResult:
        """Search the knowledge base for relevant chunks."""
        pass
