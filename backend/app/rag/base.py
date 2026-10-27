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
    title: str | None = Field(default=None, description="Title of the source document")
    source_id: str | None = Field(default=None, description="Knowledge source identifier")
    chunk_index: int | None = Field(default=None, description="Index of the chunk in document")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata tags, e.g. section, tags"
    )


class RAGTrace(BaseModel):
    """Traceability metadata for a RAG retrieval execution."""

    query: str
    embedding_provider: str
    embedding_model: str
    top_k: int
    threshold: float
    filters: dict[str, Any] = Field(default_factory=dict)
    retrieved_count: int
    duration_ms: float


class RetrievalResult(BaseModel):
    """Aggregated search result returned by retriever."""

    query: str
    chunks: list[RetrievalChunk]
    total_found: int
    trace: RAGTrace | None = None


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
