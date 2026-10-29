"""Integration tests for access control, role authorization, business invariants, and audit trail."""

import uuid
from datetime import UTC, datetime, timedelta

from app.db.models.audit_log import AuditLog
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_unauthorized_access_rejected_without_credentials(
    test_client: TestClient,
):
    """Verify that requests without credentials to protected endpoints return 401."""
    client = test_client

    for path in ["/api/v1/customers", "/api/v1/leads", "/api/v1/followups", "/api/v1/products"]:
        res = client.get(path)
        assert res.status_code == 401, f"Expected 401 for GET {path}, got {res.status_code}"
        assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_unauthorized_access_rejected_with_invalid_credentials(
    test_client: TestClient,
):
    """Verify that requests with invalid API keys or Bearer tokens return 401."""
    client = test_client

    res_bearer = client.get(
        "/api/v1/customers",
        headers={"Authorization": "Bearer invalid_secret_token_123"},
    )
    assert res_bearer.status_code == 401
    assert res_bearer.json()["error"]["code"] == "UNAUTHORIZED"

    res_apikey = client.get(
        "/api/v1/leads",
        headers={"X-API-Key": "invalid_api_key_456"},
    )
    assert res_apikey.status_code == 401
    assert res_apikey.json()["error"]["code"] == "UNAUTHORIZED"


def test_viewer_role_cannot_mutate_data(
    test_client: TestClient,
    viewer_headers: dict[str, str],
):
    """Verify that viewer role is rejected with 403 on write endpoints."""
    client = test_client

    # POST mutations are forbidden for viewer (rejected before DB layer)
    post_product = client.post(
        "/api/v1/products",
        json={"sku": "FAIL-SKU", "name": "Fail Tub", "slug": "fail-tub", "base_price": "100.00"},
        headers=viewer_headers,
    )
    assert post_product.status_code == 403
    assert post_product.json()["error"]["code"] == "FORBIDDEN"

    post_customer = client.post(
        "/api/v1/customers",
        json={"first_name": "ViewerFail", "email": "viewer@fail.com"},
        headers=viewer_headers,
    )
    assert post_customer.status_code == 403

    post_lead = client.post(
        "/api/v1/leads",
        json={"customer_id": str(uuid.uuid4())},
        headers=viewer_headers,
    )
    assert post_lead.status_code == 403

    post_followup = client.post(
        "/api/v1/followups",
        json={
            "lead_id": str(uuid.uuid4()),
            "customer_id": str(uuid.uuid4()),
            "scheduled_at": datetime.now(UTC).isoformat(),
            "reason": "Test",
        },
        headers=viewer_headers,
    )
    assert post_followup.status_code == 403


def test_agent_role_cannot_modify_products(
    unauthenticated_client_with_db: TestClient,
    agent_headers: dict[str, str],
):
    """Verify that agent role cannot modify the product catalog."""
    client = unauthenticated_client_with_db

    res_prod = client.post(
        "/api/v1/products",
        json={
            "sku": "AGENT-PROD",
            "name": "Agent Tub",
            "slug": "agent-tub",
            "base_price": "100.00",
        },
        headers=agent_headers,
    )
    assert res_prod.status_code == 403
    assert res_prod.json()["error"]["code"] == "FORBIDDEN"

    # Customer creation allowed for agent
    res_cust = client.post(
        "/api/v1/customers",
        json={
            "first_name": "AgentCreated",
            "email": f"agent.cust.{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+1 555 123 4567",
        },
        headers=agent_headers,
    )
    assert res_cust.status_code == 201
    cust_id = res_cust.json()["id"]

    # Lead creation allowed for agent
    res_lead = client.post(
        "/api/v1/leads",
        json={
            "customer_id": cust_id,
            "source": "WEBSITE",
            "interest_description": "Inquiry submitted by agent",
        },
        headers=agent_headers,
    )
    assert res_lead.status_code == 201


def test_followup_rejected_when_customer_does_not_own_lead(
    unauthenticated_client_with_db: TestClient,
    admin_headers: dict[str, str],
):
    """Verify invariant: a follow-up is rejected if customer_id does not own the referenced lead."""
    client = unauthenticated_client_with_db

    # Create Customer 1
    c1_res = client.post(
        "/api/v1/customers",
        json={"first_name": "Owner1", "email": f"owner1.{uuid.uuid4().hex[:6]}@example.com"},
        headers=admin_headers,
    )
    c1_id = c1_res.json()["id"]

    # Create Customer 2
    c2_res = client.post(
        "/api/v1/customers",
        json={"first_name": "Owner2", "email": f"owner2.{uuid.uuid4().hex[:6]}@example.com"},
        headers=admin_headers,
    )
    c2_id = c2_res.json()["id"]

    # Create Lead for Customer 1
    lead_res = client.post(
        "/api/v1/leads",
        json={"customer_id": c1_id, "source": "WEBSITE"},
        headers=admin_headers,
    )
    lead_id = lead_res.json()["id"]

    # Attempt to schedule follow-up with Customer 2 on Lead 1 (mismatched owner)
    sched_time = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    fu_res = client.post(
        "/api/v1/followups",
        json={
            "lead_id": lead_id,
            "customer_id": c2_id,
            "scheduled_at": sched_time,
            "reason": "Invalid cross-ownership follow-up",
        },
        headers=admin_headers,
    )
    assert fu_res.status_code == 422
    assert "does not own Lead" in fu_res.json()["error"]["message"]


def test_lead_rejected_when_variant_does_not_belong_to_product(
    unauthenticated_client_with_db: TestClient,
    admin_headers: dict[str, str],
):
    """Verify invariant: selecting a variant that belongs to another product is rejected."""
    client = unauthenticated_client_with_db

    # Create Product 1 with Variant
    p1_res = client.post(
        "/api/v1/products",
        json={
            "sku": f"PROD-P1-{uuid.uuid4().hex[:6]}",
            "name": "Product 1",
            "slug": f"prod-p1-{uuid.uuid4().hex[:6]}",
            "base_price": "1000.00",
            "variants": [{"name": "Variant P1", "sku_suffix": "VP1"}],
        },
        headers=admin_headers,
    )
    _ = p1_res.json()["id"]
    variant_p1_id = p1_res.json()["variants"][0]["id"]

    # Create Product 2
    p2_res = client.post(
        "/api/v1/products",
        json={
            "sku": f"PROD-P2-{uuid.uuid4().hex[:6]}",
            "name": "Product 2",
            "slug": f"prod-p2-{uuid.uuid4().hex[:6]}",
            "base_price": "2000.00",
        },
        headers=admin_headers,
    )
    p2_id = p2_res.json()["id"]

    # Create Customer
    c_res = client.post(
        "/api/v1/customers",
        json={"first_name": "LeadCust", "email": f"lc.{uuid.uuid4().hex[:6]}@example.com"},
        headers=admin_headers,
    )
    c_id = c_res.json()["id"]

    # Attempt to associate Product 2 with Variant P1 (which belongs to Product 1)
    lead_res = client.post(
        "/api/v1/leads",
        json={
            "customer_id": c_id,
            "source": "WEBSITE",
            "products": [{"product_id": p2_id, "variant_id": variant_p1_id, "quantity": 1}],
        },
        headers=admin_headers,
    )
    assert lead_res.status_code == 422
    assert "does not belong to product" in lead_res.json()["error"]["message"]


def test_duplicate_submissions_have_defined_behavior(
    unauthenticated_client_with_db: TestClient,
    admin_headers: dict[str, str],
):
    """Verify that duplicate submissions for customer, lead, and follow-up are cleanly rejected."""
    client = unauthenticated_client_with_db

    # 1. Duplicate Customer rejection
    email = f"dup.{uuid.uuid4().hex[:6]}@example.com"
    cust_payload = {"first_name": "FirstSubmission", "email": email}
    res1 = client.post("/api/v1/customers", json=cust_payload, headers=admin_headers)
    assert res1.status_code == 201
    cust_id = res1.json()["id"]

    res2 = client.post("/api/v1/customers", json=cust_payload, headers=admin_headers)
    assert res2.status_code == 422
    assert "already exists" in res2.json()["error"]["message"]

    # 2. Duplicate Active Lead rejection
    lead_payload = {
        "customer_id": cust_id,
        "source": "WEBSITE",
        "interest_description": "Duplicate inquiry test requirements",
    }
    lead_res1 = client.post("/api/v1/leads", json=lead_payload, headers=admin_headers)
    assert lead_res1.status_code == 201
    lead_id = lead_res1.json()["id"]

    lead_res2 = client.post("/api/v1/leads", json=lead_payload, headers=admin_headers)
    assert lead_res2.status_code == 422
    assert "duplicate active lead" in lead_res2.json()["error"]["message"]

    # 3. Duplicate Follow-Up scheduling rejection
    sched_time = (datetime.now(UTC) + timedelta(days=4)).isoformat()
    fu_payload = {
        "lead_id": lead_id,
        "customer_id": cust_id,
        "scheduled_at": sched_time,
        "reason": "Consultation",
    }
    fu_res1 = client.post("/api/v1/followups", json=fu_payload, headers=admin_headers)
    assert fu_res1.status_code == 201

    fu_res2 = client.post("/api/v1/followups", json=fu_payload, headers=admin_headers)
    assert fu_res2.status_code == 422
    assert "already scheduled" in fu_res2.json()["error"]["message"]


def test_mutations_recorded_in_audit_trail(
    unauthenticated_client_with_db: TestClient,
    db_session: Session,
    agent_headers: dict[str, str],
    admin_headers: dict[str, str],
):
    """Verify that important mutations (create/update) record audit trail entries with actor identity."""
    client = unauthenticated_client_with_db

    # 1. Product creation by admin
    prod_sku = f"AUDIT-PROD-{uuid.uuid4().hex[:6]}"
    p_res = client.post(
        "/api/v1/products",
        json={
            "sku": prod_sku,
            "name": "Audit Tub",
            "slug": f"audit-tub-{uuid.uuid4().hex[:6]}",
            "base_price": "5000.00",
        },
        headers=admin_headers,
    )
    assert p_res.status_code == 201
    prod_id = p_res.json()["id"]

    prod_audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "Product",
            AuditLog.entity_id == prod_id,
            AuditLog.action == "PRODUCT_CREATED",
        )
    )
    assert prod_audit is not None
    assert prod_audit.actor_id == "admin"
    assert prod_audit.actor_type == "ADMIN"

    # 2. Customer creation by sales agent
    c_res = client.post(
        "/api/v1/customers",
        json={
            "first_name": "AuditCustomer",
            "email": f"audit.c.{uuid.uuid4().hex[:6]}@example.com",
        },
        headers=agent_headers,
    )
    assert c_res.status_code == 201
    cust_id = c_res.json()["id"]

    cust_audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "Customer",
            AuditLog.entity_id == cust_id,
            AuditLog.action == "CUSTOMER_CREATED",
        )
    )
    assert cust_audit is not None
    assert cust_audit.actor_id == "sales_agent"
    assert cust_audit.actor_type == "HUMAN"
