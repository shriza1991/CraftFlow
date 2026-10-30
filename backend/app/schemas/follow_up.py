"""Pydantic schemas for FollowUps."""

from datetime import UTC, datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.db.models.enums import Channel, FollowUpStatus

PROTECTED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "approval_status",
        "approved_at",
        "approved_by",
        "delivery_status",
        "delivery_id",
        "delivery_attempts",
        "current_attempt",
        "max_retries",
        "delivery_records",
        "processed_event_ids",
        "n8n_dispatch_status",
        "n8n_dispatch_error",
        "n8n_dispatched_at",
        "schedule_version",
        "claims",
        "claim_expires_at",
        "scheduling_event_id",
    }
)


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

    @field_validator("scheduled_at")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError(
                "scheduled_at must include an explicit timezone offset (e.g. '2026-10-31T15:00:00Z' or '+00:00'). Ambiguous timezone-free datetimes are rejected."
            )
        return v.astimezone(UTC)


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

    @field_validator("scheduled_at")
    @classmethod
    def validate_timezone_aware(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError(
                "scheduled_at must include an explicit timezone offset (e.g. '2026-10-31T15:00:00Z' or '+00:00'). Ambiguous timezone-free datetimes are rejected."
            )
        return v.astimezone(UTC)


class FollowUpResponse(FollowUpBase):
    id: str
    approval_status: str = "PENDING_APPROVAL"
    delivery_status: str = "PENDING"
    delivery_id: str | None = None
    schedule_version: int = 1
    current_attempt: int = 0
    max_retries: int = 3
    n8n_dispatch_status: str = "PENDING"
    n8n_dispatch_error: str | None = None
    n8n_dispatched_at: datetime | None = None
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


class FollowUpDispatchResponse(BaseModel):
    """Response returned when triggering or retrying n8n workflow dispatch."""

    followup_id: str
    delivery_id: str | None = None
    schedule_version: int
    scheduled_at: datetime
    n8n_dispatch_status: str
    n8n_dispatch_error: str | None = None
    n8n_dispatched_at: datetime | None = None
    message: str
