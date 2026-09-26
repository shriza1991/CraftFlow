"""Conversation domain entity tracking omnichannel communication threads."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import Channel, ConversationStatus

if TYPE_CHECKING:
    from app.db.models.agent_run import AgentRun
    from app.db.models.customer import Customer
    from app.db.models.follow_up import FollowUp
    from app.db.models.message import Message


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Omnichannel interaction session session thread."""

    __tablename__ = "conversations"

    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(
        String(50), default=Channel.WEBSITE.value, nullable=False, index=True
    )
    external_conversation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(50), default=ConversationStatus.OPEN.value, nullable=False, index=True
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        "AgentRun", back_populates="conversation"
    )
    follow_ups: Mapped[list["FollowUp"]] = relationship(
        "FollowUp", back_populates="conversation"
    )
