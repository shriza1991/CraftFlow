"""FollowUp domain entity for automated and scheduled customer re-engagement."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import Channel, FollowUpStatus

if TYPE_CHECKING:
    from app.db.models.conversation import Conversation
    from app.db.models.customer import Customer
    from app.db.models.follow_up_delivery_attempt import FollowUpDeliveryAttempt
    from app.db.models.lead import Lead


class FollowUp(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Scheduled business touchpoint to nurture leads or provide quotes."""

    __tablename__ = "follow_ups"

    lead_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )

    channel: Mapped[str] = mapped_column(String(50), default=Channel.WHATSAPP.value, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default=FollowUpStatus.PENDING.value, nullable=False, index=True
    )

    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    message_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # State tracking and scheduling invariants (protected backend-owned state)
    approval_status: Mapped[str] = mapped_column(
        String(50), default="PENDING_APPROVAL", nullable=False, index=True
    )
    delivery_status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False, index=True
    )
    delivery_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    schedule_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Automation Boundary (n8n dispatch state)
    n8n_dispatch_status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False, index=True
    )
    n8n_dispatch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    n8n_dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="follow_ups")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="follow_ups")
    conversation: Mapped["Conversation | None"] = relationship(
        "Conversation", back_populates="follow_ups"
    )
    delivery_attempts: Mapped[list["FollowUpDeliveryAttempt"]] = relationship(
        "FollowUpDeliveryAttempt",
        back_populates="follow_up",
        cascade="all, delete-orphan",
        order_by="FollowUpDeliveryAttempt.attempt.asc()",
    )
