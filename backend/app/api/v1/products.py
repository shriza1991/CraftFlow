"""Product catalog management API endpoints."""

import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_admin, require_viewer_or_above
from app.core.security import AuthenticatedUser
from app.db.models.enums import ActorType
from app.schemas.pagination import PageParams, PaginatedResponse
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["Products"])


@router.get(
    "",
    response_model=PaginatedResponse[ProductResponse],
    summary="List Products",
    description="Retrieve paginated list of catalog products with optional filtering.",
)
def list_products(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    active_only: bool = Query(default=True, description="Filter only active products"),
    material: str | None = Query(default=None, description="Filter by material"),
    category: str | None = Query(default=None, description="Filter by category"),
    _user: AuthenticatedUser = Depends(require_viewer_or_above),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProductResponse]:
    params = PageParams(page=page, page_size=page_size)
    items, total = ProductService.list_products(
        db=db,
        page_params=params,
        active_only=active_only,
        material=material,
        category=category,
    )
    total_pages = math.ceil(total / params.page_size) if total > 0 else 0
    return PaginatedResponse(
        items=[ProductResponse.model_validate(p) for p in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Product",
    description="Add a product or service and optional variants. Requires admin role.",
)
def create_product(
    product_in: ProductCreate,
    user: AuthenticatedUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProductResponse:
    product = ProductService.create_product(
        db=db,
        product_in=product_in,
        actor_id=user.username,
        actor_type=ActorType.ADMIN.value,
    )
    return ProductResponse.model_validate(product)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get Product",
    description="Retrieve full details for a product including all configured variants.",
)
def get_product(
    product_id: str,
    _user: AuthenticatedUser = Depends(require_viewer_or_above),
    db: Session = Depends(get_db),
) -> ProductResponse:
    product = ProductService.get_product(db=db, product_id=product_id)
    return ProductResponse.model_validate(product)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update Product",
    description="Update product attributes, price, or active status. Requires admin role.",
)
def update_product(
    product_id: str,
    updates: ProductUpdate,
    user: AuthenticatedUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProductResponse:
    product = ProductService.update_product(
        db=db,
        product_id=product_id,
        updates=updates,
        actor_id=user.username,
        actor_type=ActorType.ADMIN.value,
    )
    return ProductResponse.model_validate(product)
