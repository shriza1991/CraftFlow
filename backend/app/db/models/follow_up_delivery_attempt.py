"""FollowUpDeliveryAttempt domain entity for concurrency-safe follow-up delivery tracking."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.follow_up import FollowUp


class FollowUpDeliveryAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Database-backed delivery attempt and execution claim record for a scheduled follow-up."""

    __tablename__ = "follow_up_delivery_attempts"

    follow_up_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("follow_ups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delivery_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schedule_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claim_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    provider: Mapped[str] = mapped_column(String(50), default="mock", nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    response_payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    # Relationships
    follow_up: Mapped["FollowUp"] = relationship("FollowUp", back_populates="delivery_attempts")

    __table_args__ = (
        UniqueConstraint(
            "delivery_id",
            "attempt",
            name="uq_follow_up_delivery_attempts_deliv_attempt",
        ),
    )
