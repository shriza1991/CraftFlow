"""FollowUp scheduling and execution API endpoints."""

import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_agent_or_admin, require_viewer_or_above
from app.core.security import AuthenticatedUser, Role
from app.db.models.enums import ActorType, FollowUpStatus
from app.schemas.follow_up import (
    FollowUpApproveRequest,
    FollowUpCancelRequest,
    FollowUpCreate,
    FollowUpResponse,
    FollowUpUpdate,
)
from app.schemas.n8n_webhook import FollowUpDeliveryStatusResponse
from app.schemas.pagination import PageParams, PaginatedResponse
from app.services.follow_up_service import FollowUpService

router = APIRouter(prefix="/followups", tags=["FollowUps"])


@router.get(
    "",
    response_model=PaginatedResponse[FollowUpResponse],
    summary="List Follow-ups",
    description="Retrieve scheduled and completed customer follow-ups.",
)
def list_followups(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: FollowUpStatus | None = Query(default=None, description="Filter by follow-up status"),
    lead_id: str | None = Query(default=None, description="Filter by lead ID"),
    _user: AuthenticatedUser = Depends(require_viewer_or_above),
    db: Session = Depends(get_db),
) -> PaginatedResponse[FollowUpResponse]:
    params = PageParams(page=page, page_size=page_size)
    items, total = FollowUpService.list_followups(
        db=db,
        page_params=params,
        status=status,
        lead_id=lead_id,
    )
    total_pages = math.ceil(total / params.page_size) if total > 0 else 0
    return PaginatedResponse(
        items=[FollowUpResponse.model_validate(f) for f in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=FollowUpResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule Follow-up",
    description="Schedule a future business follow-up touchpoint for a qualified lead.",
)
def schedule_followup(
    followup_in: FollowUpCreate,
    user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> FollowUpResponse:
    actor_type = ActorType.ADMIN.value if user.role == Role.ADMIN else ActorType.HUMAN.value
    follow_up = FollowUpService.schedule_followup(
        db=db,
        followup_in=followup_in,
        actor_id=user.username,
        actor_type=actor_type,
    )
    return FollowUpResponse.model_validate(follow_up)


@router.patch(
    "/{followup_id}",
    response_model=FollowUpResponse,
    summary="Update Follow-up",
    description="Update follow-up status (e.g. mark COMPLETED or CANCELLED with validation rules).",
)
def update_followup(
    followup_id: str,
    updates: FollowUpUpdate,
    user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> FollowUpResponse:
    actor_type = ActorType.ADMIN.value if user.role == Role.ADMIN else ActorType.HUMAN.value
    follow_up = FollowUpService.update_followup(
        db=db,
        followup_id=followup_id,
        updates=updates,
        actor_id=user.username,
        actor_type=actor_type,
    )
    return FollowUpResponse.model_validate(follow_up)


@router.post(
    "/{followup_id}/approve",
    response_model=FollowUpResponse,
    summary="Approve Follow-up",
    description="Human approval gate: approve scheduled follow-up for execution and optionally trigger n8n.",
)
async def approve_followup(
    followup_id: str,
    approval_in: FollowUpApproveRequest | None = None,
    user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> FollowUpResponse:
    actor_type = ActorType.ADMIN.value if user.role == Role.ADMIN else ActorType.HUMAN.value
    trigger_n8n = approval_in.trigger_n8n if approval_in else True
    reviewer_notes = approval_in.reviewer_notes if approval_in else None

    follow_up = await FollowUpService.approve_followup(
        db=db,
        followup_id=followup_id,
        actor_id=user.username,
        actor_type=actor_type,
        trigger_n8n=trigger_n8n,
        reviewer_notes=reviewer_notes,
    )
    return FollowUpResponse.model_validate(follow_up)


@router.post(
    "/{followup_id}/cancel",
    response_model=FollowUpResponse,
    summary="Cancel Follow-up",
    description="Cancel a scheduled follow-up preventing outbound delivery.",
)
def cancel_followup(
    followup_id: str,
    cancel_in: FollowUpCancelRequest,
    user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> FollowUpResponse:
    actor_type = ActorType.ADMIN.value if user.role == Role.ADMIN else ActorType.HUMAN.value
    follow_up = FollowUpService.cancel_followup(
        db=db,
        followup_id=followup_id,
        reason=cancel_in.reason,
        actor_id=user.username,
        actor_type=actor_type,
    )
    return FollowUpResponse.model_validate(follow_up)


@router.get(
    "/{followup_id}/delivery",
    response_model=FollowUpDeliveryStatusResponse,
    summary="Get Follow-up Delivery Status",
    description="Retrieve visible delivery status, attempts, retry bounds, and delivery audit history.",
)
def get_followup_delivery_status(
    followup_id: str,
    _user: AuthenticatedUser = Depends(require_viewer_or_above),
    db: Session = Depends(get_db),
) -> FollowUpDeliveryStatusResponse:
    return FollowUpService.get_delivery_status(db, followup_id)
