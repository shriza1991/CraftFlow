"""KnowledgeDocument domain model representing versioned business documents."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import IndexingStatus, KnowledgeDocumentStatus

if TYPE_CHECKING:
    from app.db.models.knowledge_chunk import KnowledgeChunk
    from app.db.models.knowledge_source import KnowledgeSource


class KnowledgeDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Versioned business knowledge document."""

    __tablename__ = "knowledge_documents"

    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        default=KnowledgeDocumentStatus.ACTIVE.value,
    )
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, default=dict, nullable=False
    )

    # Indexing observability
    indexing_status: Mapped[str] = mapped_column(
        String(30),
        default=IndexingStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    indexing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    source: Mapped["KnowledgeSource"] = relationship("KnowledgeSource", back_populates="documents")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index.asc()",
    )
