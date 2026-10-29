"""Unit tests for authentication, RBAC, and business invariant validations."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from app.core.exceptions import (
    ForbiddenException,
    UnauthorizedException,
    ValidationException,
)
from app.core.security import AuthenticatedUser, Role, get_current_user, require_role
from app.db.models.customer import Customer
from app.db.models.enums import CustomerSource
from app.db.models.lead import Lead
from app.db.models.product import Product, ProductVariant
from app.schemas.follow_up import FollowUpCreate
from app.schemas.lead import LeadCreate, LeadProductCreate
from app.schemas.product import ProductCreate, ProductVariantCreate
from app.services.follow_up_service import FollowUpService
from app.services.lead_service import LeadService
from app.services.product_service import ProductService
from fastapi.security import HTTPAuthorizationCredentials


def test_get_current_user_admin_key():
    """Verify admin key resolves to AuthenticatedUser with ADMIN role."""
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="cf_admin_dev_key_2026")
    user = get_current_user(api_key=None, bearer_creds=creds)
    assert user.role == Role.ADMIN
    assert user.username == "admin"


def test_get_current_user_agent_key():
    """Verify agent key via X-API-Key resolves to AGENT role."""
    user = get_current_user(api_key="cf_agent_dev_key_2026", bearer_creds=None)
    assert user.role == Role.AGENT
    assert user.username == "sales_agent"


def test_get_current_user_viewer_key():
    """Verify viewer key resolves to VIEWER role."""
    user = get_current_user(api_key="cf_viewer_dev_key_2026", bearer_creds=None)
    assert user.role == Role.VIEWER
    assert user.username == "viewer"


def test_get_current_user_missing_credentials_raises_401():
    """Verify missing credentials raise UnauthorizedException."""
    with pytest.raises(UnauthorizedException) as exc_info:
        get_current_user(api_key=None, bearer_creds=None)
    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "UNAUTHORIZED"


def test_get_current_user_invalid_credentials_raises_401():
    """Verify wrong credentials raise UnauthorizedException."""
    with pytest.raises(UnauthorizedException) as exc_info:
        get_current_user(api_key="wrong_key_xyz", bearer_creds=None)
    assert exc_info.value.status_code == 401


def test_require_role_allows_authorized_role():
    """Verify require_role passes when caller has an allowed role."""
    checker = require_role(Role.ADMIN, Role.AGENT)
    admin_user = AuthenticatedUser(id="1", username="admin", role=Role.ADMIN)
    agent_user = AuthenticatedUser(id="2", username="agent", role=Role.AGENT)

    assert checker(current_user=admin_user) == admin_user
    assert checker(current_user=agent_user) == agent_user


def test_require_role_rejects_unauthorized_role():
    """Verify require_role raises ForbiddenException for unauthorized role."""
    checker = require_role(Role.ADMIN)
    viewer_user = AuthenticatedUser(id="3", username="viewer", role=Role.VIEWER)

    with pytest.raises(ForbiddenException) as exc_info:
        checker(current_user=viewer_user)
    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "FORBIDDEN"


def test_followup_customer_lead_mismatch_raises_validation_exception():
    """Verify FollowUpService rejects mismatched lead owner without hitting real DB."""
    mock_db = MagicMock()

    lead_id = str(uuid.uuid4())
    cust1_id = str(uuid.uuid4())
    cust2_id = str(uuid.uuid4())

    mock_lead = Lead(id=lead_id, customer_id=cust1_id)
    mock_cust = Customer(id=cust2_id, first_name="Other")

    def mock_get(entity, pk):
        if entity == Lead:
            return mock_lead if pk == lead_id else None
        if entity == Customer:
            return mock_cust if pk == cust2_id else None
        return None

    mock_db.get.side_effect = mock_get

    followup_in = FollowUpCreate(
        lead_id=lead_id,
        customer_id=cust2_id,
        scheduled_at=datetime.now(UTC),
        reason="Consultation",
    )

    with pytest.raises(ValidationException) as exc_info:
        FollowUpService.schedule_followup(db=mock_db, followup_in=followup_in)
    assert "does not own Lead" in str(exc_info.value)


def test_lead_variant_product_mismatch_raises_validation_exception():
    """Verify LeadService rejects product variant that belongs to another product."""
    mock_db = MagicMock()

    cust_id = str(uuid.uuid4())
    prod1_id = str(uuid.uuid4())
    prod2_id = str(uuid.uuid4())
    variant_id = str(uuid.uuid4())

    mock_cust = Customer(id=cust_id, first_name="Test")
    mock_prod2 = Product(id=prod2_id, sku="P2", name="Prod 2", slug="p2", base_price=Decimal("10"))
    mock_variant1 = ProductVariant(id=variant_id, product_id=prod1_id, name="V1", sku_suffix="V1")

    def mock_get(entity, pk):
        if entity == Customer:
            return mock_cust if pk == cust_id else None
        if entity == Product:
            return mock_prod2 if pk == prod2_id else None
        if entity == ProductVariant:
            return mock_variant1 if pk == variant_id else None
        return None

    mock_db.get.side_effect = mock_get

    lead_in = LeadCreate(
        customer_id=cust_id,
        source=CustomerSource.WEBSITE,
        products=[LeadProductCreate(product_id=prod2_id, variant_id=variant_id)],
    )

    with pytest.raises(ValidationException) as exc_info:
        LeadService.create_lead(db=mock_db, lead_in=lead_in)
    assert "does not belong to product" in str(exc_info.value)


def test_product_duplicate_variant_suffixes_rejected():
    """Verify ProductService rejects creation with duplicate variant sku suffixes."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = None  # No existing SKU or slug

    product_in = ProductCreate(
        sku="UNIQUE-SKU",
        name="Unique Tub",
        slug="unique-tub",
        base_price=Decimal("100"),
        variants=[
            ProductVariantCreate(name="Finish A", sku_suffix="GLOSS"),
            ProductVariantCreate(name="Finish B", sku_suffix="GLOSS"),  # Duplicate suffix
        ],
    )

    with pytest.raises(ValidationException) as exc_info:
        ProductService.create_product(db=mock_db, product_in=product_in)
    assert "Duplicate variant SKU suffix" in str(exc_info.value)
