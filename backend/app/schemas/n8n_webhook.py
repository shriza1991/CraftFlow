"""Pydantic schemas for n8n webhook integration, scheduling contracts, and delivery tracking."""

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class DeliveryRecord(BaseModel):
    """Immutable audit entry for a single follow-up delivery attempt."""

    attempt_id: str = Field(..., description="Unique attempt identifier for this execution")
    delivery_id: str = Field(
        ..., description="Stable logical delivery identifier for the scheduled follow-up"
    )
    attempt: int = Field(..., ge=1, description="1-indexed attempt number")
    status: Literal["CLAIMED", "DELIVERED", "FAILED", "CANCELLED", "RETRYING", "PENDING"] = Field(
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

    @property
    def event_id(self) -> str:
        """Compatibility property for legacy event_id references."""
        return self.attempt_id


class FollowUpDeliveryStatusResponse(BaseModel):
    """Visible delivery status and attempt history for a follow-up."""

    followup_id: str
    status: str
    approval_status: str
    delivery_status: str
    delivery_id: str | None = None
    schedule_version: int = 1
    current_attempt: int = 0
    delivery_attempts: int = 0
    max_retries: int = 3
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    n8n_dispatch_status: str = "PENDING"
    n8n_dispatch_error: str | None = None
    n8n_dispatched_at: datetime | None = None
    last_event_id: str | None = None
    delivery_records: list[DeliveryRecord] = []


class N8nFollowUpEventRequest(BaseModel):
    """Inbound n8n webhook event payload defining the execution contract."""

    delivery_id: str | None = Field(
        default=None,
        description="Stable logical delivery identifier preserved across all retries of this follow-up",
    )
    attempt_id: str | None = Field(
        default=None,
        description="Unique identifier for this specific attempt (e.g. att_1_del_abc or UUID)",
    )
    event_id: str | None = Field(
        default=None,
        description="Legacy identifier accepted as attempt_id if attempt_id is omitted",
    )
    event_type: Literal["followup.execute", "followup.schedule", "followup.cancel"] = Field(
        default="followup.execute", description="Event action type"
    )
    followup_id: str = Field(..., description="Target follow-up UUID")
    schedule_version: int | None = Field(
        default=None,
        description="Version of the schedule this execution was queued for. Prevents stale execution if rescheduled.",
    )
    attempt: int = Field(default=1, ge=1, description="1-indexed current attempt number")
    max_retries: int = Field(default=3, ge=1, le=10, description="Bounded retry limit")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context, customer data, or simulation flags (e.g. simulate_failure)",
    )

    @model_validator(mode="after")
    def populate_identifiers(self) -> "N8nFollowUpEventRequest":
        """Normalize attempt_id and event_id so both are consistently available."""
        if not self.attempt_id:
            if self.event_id:
                self.attempt_id = self.event_id
            else:
                self.attempt_id = f"att_{self.attempt}_{uuid4().hex[:12]}"

        if not self.event_id:
            self.event_id = self.attempt_id

        if not self.delivery_id:
            self.delivery_id = self.event_id
        return self


class N8nFollowUpEventResponse(BaseModel):
    """Outbound response to n8n after processing event."""

    delivery_id: str
    attempt_id: str
    event_id: str
    followup_id: str
    schedule_version: int = 1
    status: Literal[
        "DELIVERED",
        "FAILED",
        "RETRYING",
        "NOT_DUE",
        "DUPLICATE_REPLAY",
        "DUPLICATE_IGNORED",
        "ALREADY_COMPLETED",
        "CANCELLED",
        "UNAPPROVED",
        "STALE_SCHEDULE",
        "CLAIM_ACTIVE",
    ]
    delivery_status: str
    attempt: int
    max_retries: int
    retryable: bool = False
    next_eligible_at: datetime | None = None
    message: str
    duplicate: bool = False
    delivery_record: DeliveryRecord | None = None
    timestamp: datetime
