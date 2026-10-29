"""Customer profile management API endpoints."""

import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_agent_or_admin, require_viewer_or_above
from app.core.security import AuthenticatedUser, Role
from app.db.models.enums import ActorType
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate
from app.schemas.pagination import PageParams, PaginatedResponse
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get(
    "",
    response_model=PaginatedResponse[CustomerResponse],
    summary="List Customers",
    description="Search and list customers across all acquisition channels.",
)
def list_customers(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(
        default=None, description="Search by name, email, phone, or company"
    ),
    active_only: bool = Query(default=True, description="Filter only active customers"),
    _user: AuthenticatedUser = Depends(require_viewer_or_above),
    db: Session = Depends(get_db),
) -> PaginatedResponse[CustomerResponse]:
    params = PageParams(page=page, page_size=page_size)
    items, total = CustomerService.list_customers(
        db=db,
        page_params=params,
        search=search,
        active_only=active_only,
    )
    total_pages = math.ceil(total / params.page_size) if total > 0 else 0
    return PaginatedResponse(
        items=[CustomerResponse.model_validate(c) for c in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Customer",
    description="Create a new customer profile with automatic international phone and email normalization.",
)
def create_customer(
    customer_in: CustomerCreate,
    user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> CustomerResponse:
    actor_type = ActorType.ADMIN.value if user.role == Role.ADMIN else ActorType.HUMAN.value
    customer = CustomerService.create_customer(
        db=db,
        customer_in=customer_in,
        actor_id=user.username,
        actor_type=actor_type,
    )
    return CustomerResponse.model_validate(customer)


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Get Customer",
    description="Retrieve customer profile by ID.",
)
def get_customer(
    customer_id: str,
    _user: AuthenticatedUser = Depends(require_viewer_or_above),
    db: Session = Depends(get_db),
) -> CustomerResponse:
    customer = CustomerService.get_customer(db=db, customer_id=customer_id)
    return CustomerResponse.model_validate(customer)


@router.patch(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update Customer",
    description="Update customer details or contact information.",
)
def update_customer(
    customer_id: str,
    updates: CustomerUpdate,
    user: AuthenticatedUser = Depends(require_agent_or_admin),
    db: Session = Depends(get_db),
) -> CustomerResponse:
    actor_type = ActorType.ADMIN.value if user.role == Role.ADMIN else ActorType.HUMAN.value
    customer = CustomerService.update_customer(
        db=db,
        customer_id=customer_id,
        updates=updates,
        actor_id=user.username,
        actor_type=actor_type,
    )
    return CustomerResponse.model_validate(customer)
