"""Sales lead pipeline management API endpoints."""

import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_agent_or_admin, require_viewer_or_above
from app.core.security import AuthenticatedUser, Role
from app.db.models.enums import ActorType, LeadStatus
from app.schemas.lead import LeadCreate, LeadResponse, LeadUpdate
from app.schemas.pagination import PageParams, PaginatedResponse
from app.services.lead_service import LeadService

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get(
    "",
    response_model=PaginatedResponse[LeadResponse],
    summary="List Leads",
    description="Retrieve paginated list of qualified sales leads with optional status filtering.",
)
def list_leads(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: LeadStatus | None = Query(
        default=None, description="Filter by lead qualification status"
    ),
    customer_id: str | None = Query(default=None, description="Filter by customer ID"),
    _user: AuthenticatedUser = Depends(require_viewer_or_above),
    db: Session = Depends(get_db),
) -> PaginatedResponse[LeadResponse]:
    params = PageParams(page=page, page_size=page_size)
    items, total = LeadService.list_leads(
        db=db,
        page_params=params,
        status=status,
        customer_id=customer_id,
    )
    total_pages = math.ceil(total / params.page_size) if total > 0 else 0
    return PaginatedResponse(
        items=[LeadResponse.model_validate(lead) for lead in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Lead",
    description="Record a new sales opportunity linked to a customer and interested products.",
)
def create_lead(
    lead_in: LeadCreate,
    user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> LeadResponse:
    actor_type = ActorType.ADMIN.value if user.role == Role.ADMIN else ActorType.HUMAN.value
    lead = LeadService.create_lead(
        db=db,
        lead_in=lead_in,
        actor_id=user.username,
        actor_type=actor_type,
    )
    return LeadResponse.model_validate(lead)


@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Get Lead",
    description="Retrieve lead details including associated products and qualification scores.",
)
def get_lead(
    lead_id: str,
    _user: AuthenticatedUser = Depends(require_viewer_or_above),
    db: Session = Depends(get_db),
) -> LeadResponse:
    lead = LeadService.get_lead(db=db, lead_id=lead_id)
    return LeadResponse.model_validate(lead)


@router.patch(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Update Lead",
    description="Update lead details or advance pipeline status (enforcing deterministic transition rules).",
)
def update_lead(
    lead_id: str,
    updates: LeadUpdate,
    user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> LeadResponse:
    actor_type = ActorType.ADMIN.value if user.role == Role.ADMIN else ActorType.HUMAN.value
    lead = LeadService.update_lead(
        db=db,
        lead_id=lead_id,
        updates=updates,
        actor_id=user.username,
        actor_type=actor_type,
    )
    return LeadResponse.model_validate(lead)
