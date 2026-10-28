"""Pydantic schemas for RAG query requests, grounded answers, and source citations."""

from typing import Any

from pydantic import BaseModel, Field

from app.rag.base import RAGTrace


class RAGSourceCitation(BaseModel):
    """Source citation identifying the exact document and chunk with provenance metadata."""

    document_id: str
    chunk_id: str
    title: str | None = None
    score: float
    source_id: str | None = None
    source_name: str | None = None
    chunk_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGQueryRequest(BaseModel):
    """Natural-language question sent to the RAG knowledge assistant."""

    question: str = Field(
        ...,
        min_length=1,
        description="Question about business services, products, guides, or policies",
    )
    top_k: int = Field(default=4, ge=1, le=20, description="Max knowledge snippets to retrieve")
    threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Optional minimum similarity score"
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional filters: document_type, source_id, language, product_id",
    )


class RAGQueryResponse(BaseModel):
    """Grounded answer from the RAG knowledge assistant."""

    answer: str
    grounded: bool = Field(
        ...,
        description=(
            "Whether the answer was synthesized from retrieved business context. "
            "Note: grounded=True indicates the response was conditioned on retrieved evidence, "
            "not that the factual claims have been independently or externally verified."
        ),
    )
    sources: list[RAGSourceCitation] = Field(
        default_factory=list,
        description="Source citations from retrieved knowledge chunks supporting the response",
    )
    retrieval_count: int = Field(
        default=0, description="Number of chunks retrieved passing threshold"
    )
    trace: RAGTrace | None = None
