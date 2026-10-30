"""Integration tests for n8n webhook API, approval endpoints, and delivery observability."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.db.models.customer import Customer
from app.db.models.enums import Channel, LeadPriority, LeadStatus
from app.db.models.lead import Lead
from app.schemas.follow_up import FollowUpCreate
from app.services.follow_up_service import FollowUpService
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

settings = get_settings()
WEBHOOK_SECRET = settings.N8N_WEBHOOK_SECRET


@pytest.fixture
def test_data(db_session: Session) -> tuple[Customer, Lead]:
    """Helper fixture to create test customer and lead."""
    customer = Customer(
        first_name="Marcus",
        last_name="Flynn",
        email=f"marcus.{uuid4().hex[:6]}@example.com",
        phone=f"+1415555{uuid4().hex[:4]}",
        source="WEBSITE",
    )
    db_session.add(customer)
    db_session.flush()

    lead = Lead(
        customer_id=customer.id,
        interest_description="Custom marble architectural basin",
        status=LeadStatus.QUALIFIED.value,
        priority=LeadPriority.MEDIUM.value,
        estimated_value=12000.00,
    )
    db_session.add(lead)
    db_session.commit()
    return customer, lead


def test_webhook_unauthenticated_rejected(
    unauthenticated_client_with_db: TestClient, test_data: tuple[Customer, Lead]
):
    """Verify that incoming n8n webhook without valid secret is rejected with 401."""
    client = unauthenticated_client_with_db
    _customer, lead = test_data

    payload = {
        "event_id": f"evt_{uuid4().hex[:8]}",
        "event_type": "followup.execute",
        "followup_id": lead.id,
    }

    # Missing header
    res = client.post("/api/v1/webhooks/n8n", json=payload)
    assert res.status_code == 401
    data = res.json()
    assert data["error"]["code"] == "WEBHOOK_AUTHENTICATION_FAILED"

    # Invalid header
    res2 = client.post(
        "/api/v1/webhooks/n8n",
        json=payload,
        headers={"X-Webhook-Secret": "invalid_secret_token"},
    )
    assert res2.status_code == 401


def test_followup_approval_and_cancel_rbac(
    unauthenticated_client_with_db: TestClient,
    agent_headers: dict[str, str],
    viewer_headers: dict[str, str],
    db_session: Session,
    test_data: tuple[Customer, Lead],
):
    """Verify RBAC permissions on follow-up approve and cancel endpoints."""
    client = unauthenticated_client_with_db
    customer, lead = test_data

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=2),
        reason="Verify site access.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")

    # 1. Unauthenticated -> 401
    res = client.post(f"/api/v1/followups/{fu.id}/approve")
    assert res.status_code == 401

    # 2. Viewer -> 403 (Mutation forbidden)
    res_viewer = client.post(f"/api/v1/followups/{fu.id}/approve", headers=viewer_headers)
    assert res_viewer.status_code == 403

    # 3. Agent -> 200 (Authorized)
    res_agent = client.post(
        f"/api/v1/followups/{fu.id}/approve",
        headers=agent_headers,
        json={"trigger_n8n": False, "reviewer_notes": "Approved by sales lead."},
    )
    assert res_agent.status_code == 200
    assert res_agent.json()["approval_status"] == "APPROVED"

    # 4. Cancel via Agent -> 200
    res_cancel = client.post(
        f"/api/v1/followups/{fu.id}/cancel",
        headers=agent_headers,
        json={"reason": "Customer postponed."},
    )
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELLED"
    assert res_cancel.json()["approval_status"] == "CANCELLED"


def test_full_n8n_followup_http_lifecycle(
    unauthenticated_client_with_db: TestClient,
    agent_headers: dict[str, str],
    viewer_headers: dict[str, str],
    test_data: tuple[Customer, Lead],
):
    """Verify full HTTP lifecycle: schedule -> early execution blocked -> approve -> reschedule -> due execution -> idempotent replay."""
    client = unauthenticated_client_with_db
    customer, lead = test_data

    # Step 1: Schedule follow-up via HTTP API for 3 hours in future
    future_time = datetime.now(UTC) + timedelta(hours=3)
    schedule_payload = {
        "lead_id": lead.id,
        "customer_id": customer.id,
        "channel": "WHATSAPP",
        "scheduled_at": future_time.isoformat(),
        "reason": "Confirm delivery date and site readiness.",
        "message_template": "Hi Marcus, checking in on delivery logistics for your custom basin.",
    }
    sched_res = client.post("/api/v1/followups", headers=agent_headers, json=schedule_payload)
    assert sched_res.status_code == 201
    sched_data = sched_res.json()
    followup_id = sched_data["id"]
    initial_delivery_id = sched_data["delivery_id"]
    initial_version = sched_data["schedule_version"]

    # Step 2: Attempt n8n execution before approval -> UNAPPROVED
    evt_id_1 = f"evt_{uuid4().hex[:10]}"
    webhook_payload_1 = {
        "event_id": evt_id_1,
        "event_type": "followup.execute",
        "followup_id": followup_id,
        "delivery_id": initial_delivery_id,
        "attempt_id": f"att_unapp_{uuid4().hex[:6]}",
        "schedule_version": initial_version,
        "attempt": 1,
        "max_retries": 3,
    }
    unappr_res = client.post(
        "/api/v1/webhooks/n8n",
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
        json=webhook_payload_1,
    )
    assert unappr_res.status_code == 200
    assert unappr_res.json()["status"] == "UNAPPROVED"

    # Step 3: Approve follow-up via HTTP API
    appr_res = client.post(
        f"/api/v1/followups/{followup_id}/approve",
        headers=agent_headers,
        json={"trigger_n8n": False, "reviewer_notes": "Logistics confirmed."},
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["approval_status"] == "APPROVED"

    # Step 4: Early execution before due date -> NOT_DUE
    early_res = client.post(
        "/api/v1/webhooks/n8n",
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
        json={
            "event_id": f"evt_{uuid4().hex[:8]}",
            "event_type": "followup.execute",
            "followup_id": followup_id,
            "delivery_id": initial_delivery_id,
            "attempt_id": f"att_early_{uuid4().hex[:6]}",
            "schedule_version": initial_version,
            "attempt": 1,
        },
    )
    assert early_res.status_code == 200
    early_data = early_res.json()
    assert early_data["status"] == "NOT_DUE"
    assert early_data["next_eligible_at"] is not None
    assert early_data["delivery_record"] is None

    # Step 5: Reschedule follow-up to past (due time) via PATCH
    past_time = datetime.now(UTC) - timedelta(minutes=5)
    update_res = client.patch(
        f"/api/v1/followups/{followup_id}",
        headers=agent_headers,
        json={"scheduled_at": past_time.isoformat()},
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    new_delivery_id = updated_data["delivery_id"]
    new_version = updated_data["schedule_version"]
    assert new_version == initial_version + 1
    assert new_delivery_id != initial_delivery_id

    # Step 6: Older execution call with stale version/delivery_id -> STALE_SCHEDULE
    stale_res = client.post(
        "/api/v1/webhooks/n8n",
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
        json={
            "event_id": f"evt_{uuid4().hex[:8]}",
            "event_type": "followup.execute",
            "followup_id": followup_id,
            "delivery_id": initial_delivery_id,
            "attempt_id": f"att_stale_{uuid4().hex[:6]}",
            "schedule_version": initial_version,
            "attempt": 1,
        },
    )
    assert stale_res.status_code == 200
    assert stale_res.json()["status"] == "STALE_SCHEDULE"

    # Step 7: n8n relays execution event for active delivery_id -> DELIVERED
    attempt_id_active = f"att_due_{uuid4().hex[:8]}"
    webhook_payload_due = {
        "event_id": f"evt_{uuid4().hex[:8]}",
        "event_type": "followup.execute",
        "followup_id": followup_id,
        "delivery_id": new_delivery_id,
        "attempt_id": attempt_id_active,
        "schedule_version": new_version,
        "attempt": 1,
        "max_retries": 3,
    }
    exec_res = client.post(
        "/api/v1/webhooks/n8n",
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
        json=webhook_payload_due,
    )
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "DELIVERED"
    assert exec_data["delivery_status"] == "DELIVERED"
    assert exec_data["delivery_record"]["provider_message_id"] is not None

    # Step 8: Repeated attempt is returned as DUPLICATE_REPLAY
    replay_res = client.post(
        "/api/v1/webhooks/n8n",
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
        json=webhook_payload_due,
    )
    assert replay_res.status_code == 200
    assert replay_res.json()["status"] == "DUPLICATE_REPLAY"
    assert replay_res.json()["duplicate"] is True

    # Step 9: Viewer inspects delivery status via GET /delivery
    deliv_res = client.get(
        f"/api/v1/followups/{followup_id}/delivery",
        headers=viewer_headers,
    )
    assert deliv_res.status_code == 200
    deliv_data = deliv_res.json()
    assert deliv_data["status"] == "COMPLETED"
    assert deliv_data["approval_status"] == "APPROVED"
    assert deliv_data["delivery_status"] == "DELIVERED"
    assert len(deliv_data["delivery_records"]) == 1


def test_retry_dispatch_endpoint_rbac_and_behavior(
    unauthenticated_client_with_db: TestClient,
    agent_headers: dict[str, str],
    viewer_headers: dict[str, str],
    db_session: Session,
    test_data: tuple[Customer, Lead],
):
    """Verify POST /api/v1/followups/{id}/retry-dispatch permissions and functionality."""
    client = unauthenticated_client_with_db
    customer, lead = test_data

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=2),
        reason="Verify crate dimensions.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")

    # 1. Unauthenticated -> 401
    res = client.post(f"/api/v1/followups/{fu.id}/retry-dispatch")
    assert res.status_code == 401

    # 2. Viewer -> 403
    res_viewer = client.post(
        f"/api/v1/followups/{fu.id}/retry-dispatch",
        headers=viewer_headers,
    )
    assert res_viewer.status_code == 403

    # 3. Unapproved follow-up -> 422 (Must be approved before dispatching)
    res_unappr = client.post(
        f"/api/v1/followups/{fu.id}/retry-dispatch",
        headers=agent_headers,
    )
    assert res_unappr.status_code == 422
    assert "must be approved" in res_unappr.json()["error"]["message"].lower()

    # 4. Approve follow-up
    client.post(
        f"/api/v1/followups/{fu.id}/approve",
        headers=agent_headers,
        json={"trigger_n8n": False},
    )

    # 5. Agent retries dispatch -> 200
    res_retry = client.post(
        f"/api/v1/followups/{fu.id}/retry-dispatch",
        headers=agent_headers,
    )
    assert res_retry.status_code == 200
    retry_data = res_retry.json()
    assert retry_data["n8n_dispatch_status"] == "DISPATCHED"
    assert retry_data["delivery_id"] == fu.delivery_id
