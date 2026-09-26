"""AuditLog domain entity maintaining an immutable audit trail."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, UUIDPrimaryKeyMixin
from app.db.models.enums import ActorType


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail recording state changes and security events."""

    __tablename__ = "audit_logs"

    actor_type: Mapped[str] = mapped_column(
        String(50), default=ActorType.SYSTEM.value, nullable=False
    )
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_state: Mapped[dict | None] = mapped_column("before_state", JSONType, nullable=True)
    after_state: Mapped[dict | None] = mapped_column("after_state", JSONType, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
