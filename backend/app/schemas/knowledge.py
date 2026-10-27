"""Pydantic schemas for Knowledge Sources, Documents, and Chunks."""

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.db.models.enums import IndexingStatus, KnowledgeDocumentStatus, KnowledgeSourceType
from app.rag.base import RAGTrace, RetrievalChunk


# ------------------------------------------------------------------------------
# Knowledge Source Schemas
# ------------------------------------------------------------------------------
class KnowledgeSourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    source_type: KnowledgeSourceType = KnowledgeSourceType.OTHER
    description: str | None = Field(default=None, max_length=500)
    uri: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class KnowledgeSourceCreate(KnowledgeSourceBase):
    pass


class KnowledgeSourceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    source_type: KnowledgeSourceType | None = None
    description: str | None = Field(default=None, max_length=500)
    uri: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class KnowledgeSourceResponse(KnowledgeSourceBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ------------------------------------------------------------------------------
# Knowledge Document Schemas
# ------------------------------------------------------------------------------
class KnowledgeDocumentBase(BaseModel):
    source_id: str
    title: str = Field(..., min_length=1, max_length=255)
    document_type: str = Field(default="GENERAL", max_length=50)
    content: str = Field(..., min_length=1)
    version: int = Field(default=1, ge=1)
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.ACTIVE
    language: str = Field(default="en", max_length=10)
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class KnowledgeDocumentCreate(KnowledgeDocumentBase):
    pass


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    document_type: str | None = None
    content: str | None = None
    status: KnowledgeDocumentStatus | None = None
    language: str | None = None
    metadata_: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class KnowledgeDocumentResponse(KnowledgeDocumentBase):
    id: str
    checksum: str
    indexing_status: IndexingStatus
    indexing_error: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ------------------------------------------------------------------------------
# Search Endpoint Schemas
# ------------------------------------------------------------------------------
class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language search query")
    top_k: int = Field(default=4, ge=1, le=50, description="Max number of chunks to return")
    threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Minimum cosine similarity score"
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata filters: document_type, source_id, language, product_id",
    )


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[RetrievalChunk]
    total_found: int
    trace: RAGTrace | None = None
