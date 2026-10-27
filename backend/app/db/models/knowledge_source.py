"""KnowledgeSource domain model representing origin repositories of business information."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import KnowledgeSourceType

if TYPE_CHECKING:
    from app.db.models.knowledge_document import KnowledgeDocument


class KnowledgeSource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Origin source of business knowledge (e.g., catalog, policies, guides)."""

    __tablename__ = "knowledge_sources"

    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        default=KnowledgeSourceType.OTHER.value,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    documents: Mapped[list["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument",
        back_populates="source",
        cascade="all, delete-orphan",
        order_by="KnowledgeDocument.created_at.desc()",
    )
