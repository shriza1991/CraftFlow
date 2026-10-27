"""Message domain entity representing customer and agent message records."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import MessageDirection, MessageStatus, MessageType, SenderType

if TYPE_CHECKING:
    from app.db.models.conversation import Conversation


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Individual message exchanged in a conversation."""

    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    direction: Mapped[str] = mapped_column(
        String(20), default=MessageDirection.INBOUND.value, nullable=False, index=True
    )
    message_type: Mapped[str] = mapped_column(
        String(20), default=MessageType.TEXT.value, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sender_type: Mapped[str] = mapped_column(
        String(50), default=SenderType.CUSTOMER.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), default=MessageStatus.RECEIVED.value, nullable=False
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
