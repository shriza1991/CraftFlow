"""Pydantic schemas for Messages."""

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.db.models.enums import MessageDirection, MessageStatus, MessageType, SenderType


class MessageBase(BaseModel):
    direction: MessageDirection = MessageDirection.INBOUND
    message_type: MessageType = MessageType.TEXT
    content: str = Field(..., min_length=1)
    sender_type: SenderType = SenderType.CUSTOMER
    status: MessageStatus = MessageStatus.RECEIVED
    external_message_id: str | None = None
    sent_at: datetime | None = None
    received_at: datetime | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class MessageCreate(BaseModel):
    direction: MessageDirection = MessageDirection.INBOUND
    message_type: MessageType = MessageType.TEXT
    content: str = Field(..., min_length=1)
    sender_type: SenderType = SenderType.CUSTOMER
    status: MessageStatus = MessageStatus.RECEIVED
    external_message_id: str | None = None
    sent_at: datetime | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class MessageResponse(MessageBase):
    id: str
    conversation_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
