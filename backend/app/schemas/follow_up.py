"""Pydantic schemas for FollowUps."""

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.db.models.enums import Channel, FollowUpStatus


class FollowUpBase(BaseModel):
    lead_id: str
    customer_id: str
    conversation_id: str | None = None
    channel: Channel = Channel.WHATSAPP
    scheduled_at: datetime
    status: FollowUpStatus = FollowUpStatus.PENDING
    reason: str = Field(..., min_length=1, max_length=255)
    message_template: str | None = None
    failure_reason: str | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class FollowUpCreate(FollowUpBase):
    pass


class FollowUpUpdate(BaseModel):
    status: FollowUpStatus | None = None
    scheduled_at: datetime | None = None
    reason: str | None = None
    message_template: str | None = None
    failure_reason: str | None = None
    metadata_: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class FollowUpResponse(FollowUpBase):
    id: str
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FollowUpApproveRequest(BaseModel):
    """Request payload to approve a scheduled follow-up."""

    trigger_n8n: bool = Field(
        default=True, description="Whether to trigger external n8n workflow upon approval"
    )
    reviewer_notes: str | None = Field(
        default=None, description="Optional notes from the approving reviewer"
    )


class FollowUpCancelRequest(BaseModel):
    """Request payload to cancel a scheduled follow-up."""

    reason: str = Field(
        ..., min_length=1, max_length=500, description="Reason for cancelling the follow-up"
    )
