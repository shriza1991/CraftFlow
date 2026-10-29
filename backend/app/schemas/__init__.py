"""Pydantic schemas package."""

from app.schemas.follow_up import (
    FollowUpApproveRequest,
    FollowUpCancelRequest,
    FollowUpCreate,
    FollowUpResponse,
    FollowUpUpdate,
)
from app.schemas.inquiry import (
    CustomerIntake,
    DraftResponse,
    EvidenceCitation,
    InquiryApprovalRequest,
    InquiryRejectionRequest,
    InquiryRequest,
    InquiryWorkflowResponse,
    WorkflowStepResult,
)
from app.schemas.n8n_webhook import (
    DeliveryRecord,
    FollowUpDeliveryStatusResponse,
    N8nFollowUpEventRequest,
    N8nFollowUpEventResponse,
)

__all__ = [
    "CustomerIntake",
    "DeliveryRecord",
    "DraftResponse",
    "EvidenceCitation",
    "FollowUpApproveRequest",
    "FollowUpCancelRequest",
    "FollowUpCreate",
    "FollowUpDeliveryStatusResponse",
    "FollowUpResponse",
    "FollowUpUpdate",
    "InquiryApprovalRequest",
    "InquiryRejectionRequest",
    "InquiryRequest",
    "InquiryWorkflowResponse",
    "N8nFollowUpEventRequest",
    "N8nFollowUpEventResponse",
    "WorkflowStepResult",
]
