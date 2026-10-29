"""Pydantic schemas for n8n webhook integration and follow-up delivery tracking."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DeliveryRecord(BaseModel):
    """Immutable audit entry for a single follow-up delivery attempt."""

    event_id: str = Field(..., description="Unique event identifier triggering this attempt")
    attempt: int = Field(..., ge=1, description="Attempt number")
    status: Literal["DELIVERED", "FAILED", "PENDING", "RETRYING"] = Field(
        ..., description="Result of this specific attempt"
    )
    timestamp: datetime = Field(..., description="UTC timestamp of the delivery attempt")
    provider: str = Field(
        default="mock", description="Messaging provider used (e.g. 'mock', 'whatsapp')"
    )
    provider_message_id: str | None = Field(
        default=None, description="External provider message ID"
    )
    recipient: str | None = Field(default=None, description="Destination phone number or email")
    error: str | None = Field(default=None, description="Error details if attempt failed")
    retryable: bool = Field(default=False, description="Whether this attempt can be retried")


class FollowUpDeliveryStatusResponse(BaseModel):
    """Visible delivery status and attempt history for a follow-up."""

    followup_id: str
    status: str
    approval_status: str
    delivery_status: str
    delivery_attempts: int
    max_retries: int
    completed_at: datetime | None = None
    failure_reason: str | None = None
    last_event_id: str | None = None
    delivery_records: list[DeliveryRecord] = []


class N8nFollowUpEventRequest(BaseModel):
    """Inbound n8n webhook event payload."""

    event_id: str = Field(..., min_length=1, description="Unique event identifier for idempotency")
    event_type: Literal["followup.execute", "followup.schedule", "followup.cancel"] = Field(
        default="followup.execute", description="Event action type"
    )
    followup_id: str = Field(..., description="Target follow-up UUID")
    attempt: int = Field(default=1, ge=1, description="Current attempt number")
    max_retries: int = Field(default=3, ge=1, le=10, description="Bounded retry limit")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Additional context, customer data, or simulation flags"
    )


class N8nFollowUpEventResponse(BaseModel):
    """Outbound response to n8n after processing event."""

    event_id: str
    followup_id: str
    status: Literal[
        "DELIVERED",
        "FAILED",
        "RETRYING",
        "DUPLICATE_IGNORED",
        "ALREADY_COMPLETED",
        "CANCELLED",
        "UNAPPROVED",
    ]
    delivery_status: str
    attempt: int
    max_retries: int
    retryable: bool = False
    message: str
    duplicate: bool = False
    delivery_record: DeliveryRecord | None = None
    timestamp: datetime
