"""Pydantic schemas for end-to-end customer inquiry workflow and approval gates."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.db.models.enums import Channel, CustomerSource


class CustomerIntake(BaseModel):
    """Customer identity provided with an inquiry."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    whatsapp_number: str | None = Field(default=None, max_length=50)
    company_name: str | None = Field(default=None, max_length=255)
    source: CustomerSource = CustomerSource.WEBSITE


class InquiryRequest(BaseModel):
    """Inbound customer inquiry request."""

    message: str = Field(
        ..., min_length=1, description="Customer question, requirement, or project description"
    )
    customer_id: str | None = Field(
        default=None, description="Existing customer ID if already known"
    )
    customer: CustomerIntake | None = Field(
        default=None, description="Customer details if customer_id is not supplied"
    )
    channel: Channel = Field(default=Channel.WEBSITE, description="Inquiry communication channel")
    preferred_product_skus: list[str] = Field(
        default_factory=list, description="Optional explicit product SKUs referenced in inquiry"
    )
    metadata_: dict[str, Any] = Field(default_factory=dict, description="Arbitrary client metadata")


class EvidenceCitation(BaseModel):
    """Traceable provenance citation referencing verified knowledge or catalog facts."""

    type: str = Field(..., description="'knowledge' or 'catalog'")
    title: str | None = None
    source_name: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    score: float | None = None
    sku: str | None = None
    product_name: str | None = None
    material: str | None = None
    price: str | None = None
    lead_time_days: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DraftResponse(BaseModel):
    """Drafted outbound message pending human review."""

    content: str
    grounded: bool
    evidence_sources: list[EvidenceCitation] = Field(default_factory=list)
    approval_status: str = Field(
        default="PENDING_APPROVAL", description="'PENDING_APPROVAL', 'APPROVED', or 'REJECTED'"
    )
    message_id: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None


class WorkflowStepResult(BaseModel):
    """Individual workflow step execution status and diagnostics."""

    step_name: str
    status: str = Field(
        ...,
        description="'COMPLETED', 'INSUFFICIENT_EVIDENCE', 'PENDING_APPROVAL', 'FAILED', or 'SKIPPED'",
    )
    started_at: datetime
    completed_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class InquiryWorkflowResponse(BaseModel):
    """Complete traceable outcome of processing an inquiry."""

    workflow_run_id: str = Field(..., description="Unique AgentRun ID tracking this workflow")
    status: str = Field(
        ..., description="Overall workflow status: 'COMPLETED', 'NEEDS_REVIEW', or 'FAILED'"
    )
    customer_id: str
    conversation_id: str
    lead_id: str | None = None
    draft: DraftResponse | None = None
    outbound_message_sent: bool = Field(
        default=False, description="Whether an outbound customer message has been dispatched"
    )
    steps: list[WorkflowStepResult] = Field(default_factory=list)
    error: str | None = None


class InquiryApprovalRequest(BaseModel):
    """Human approval request to confirm and dispatch a drafted response."""

    edited_content: str | None = Field(
        default=None,
        description="Optional edited text. If omitted, the drafted content is sent as-is.",
    )


class InquiryRejectionRequest(BaseModel):
    """Human rejection request declining to send a drafted response."""

    reason: str | None = Field(default=None, description="Optional explanation for rejection")
