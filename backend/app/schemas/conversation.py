"""Pydantic schemas for Conversations."""

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.db.models.enums import Channel, ConversationStatus
from app.schemas.message import MessageResponse


class ConversationBase(BaseModel):
    customer_id: str
    channel: Channel = Channel.WEBSITE
    external_conversation_id: str | None = None
    status: ConversationStatus = ConversationStatus.OPEN
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class ConversationCreate(ConversationBase):
    pass


class ConversationResponse(ConversationBase):
    id: str
    started_at: datetime
    last_message_at: datetime | None = None
    ended_at: datetime | None = None
    messages: list[MessageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
