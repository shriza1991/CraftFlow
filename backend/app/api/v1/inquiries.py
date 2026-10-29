"""API endpoints for the end-to-end customer inquiry workflow and human approval gates."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import (
    AuthenticatedUser,
    get_db,
    require_agent_or_admin,
    require_viewer_or_above,
)
from app.schemas.inquiry import (
    InquiryApprovalRequest,
    InquiryRejectionRequest,
    InquiryRequest,
    InquiryWorkflowResponse,
)
from app.services.inquiry_service import InquiryService

router = APIRouter(prefix="/inquiries", tags=["Inquiries & Approvals"])


@router.post(
    "",
    response_model=InquiryWorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Accept and process a customer inquiry",
    description=(
        "Processes an inbound customer inquiry: gathers customer context, performs "
        "grounded knowledge and catalog retrieval, drafts a referenced response, and "
        "creates or updates a lead. The outbound customer message is held for human approval."
    ),
)
async def process_inquiry(
    request: InquiryRequest,
    current_user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> InquiryWorkflowResponse:
    """Accept and process a customer inquiry without dispatching outbound message."""
    return await InquiryService.process_inquiry(
        db=db,
        request=request,
        actor_id=current_user.actor_id,
        actor_type=current_user.actor_type,
    )


@router.get(
    "/{run_id}",
    response_model=InquiryWorkflowResponse,
    summary="Get inquiry workflow status and draft",
    description="Retrieve the execution status, steps, draft response, and lead for an inquiry run.",
)
def get_inquiry(
    run_id: str,
    current_user: AuthenticatedUser = Depends(require_viewer_or_above),
    db: Session = Depends(get_db),
) -> InquiryWorkflowResponse:
    """Get the current state and step execution log for an inquiry run."""
    return InquiryService.get_inquiry_status(db=db, workflow_run_id=run_id)


@router.post(
    "/{run_id}/approve",
    response_model=InquiryWorkflowResponse,
    summary="Approve and dispatch drafted response",
    description=(
        "Human approval gate: approves the drafted response (with optional edits) "
        "and dispatches the outbound message to the customer."
    ),
)
async def approve_inquiry(
    run_id: str,
    approval_in: InquiryApprovalRequest | None = None,
    current_user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> InquiryWorkflowResponse:
    """Approve inquiry response draft and send outbound message."""
    edited_content = approval_in.edited_content if approval_in else None
    return await InquiryService.approve_inquiry(
        db=db,
        workflow_run_id=run_id,
        edited_content=edited_content,
        actor_id=current_user.actor_id,
        actor_type=current_user.actor_type,
    )


@router.post(
    "/{run_id}/reject",
    response_model=InquiryWorkflowResponse,
    summary="Reject drafted response",
    description="Declines to send the drafted response. Prevents outbound message dispatch.",
)
def reject_inquiry(
    run_id: str,
    rejection_in: InquiryRejectionRequest | None = None,
    current_user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> InquiryWorkflowResponse:
    """Reject inquiry draft."""
    reason = rejection_in.reason if rejection_in else None
    return InquiryService.reject_inquiry(
        db=db,
        workflow_run_id=run_id,
        reason=reason,
        actor_id=current_user.actor_id,
        actor_type=current_user.actor_type,
    )
