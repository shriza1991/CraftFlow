"""Integration tests for the customer inquiry API, approval gates, and RBAC permissions."""

import uuid

from fastapi.testclient import TestClient


def test_unauthorized_inquiry_endpoints_rejected(test_client: TestClient):
    """Verify that inquiry endpoints require authentication."""
    client = test_client

    # Without credentials -> 401
    res_post = client.post("/api/v1/inquiries", json={"message": "Hello"})
    assert res_post.status_code == 401
    assert res_post.json()["error"]["code"] == "UNAUTHORIZED"

    res_get = client.get(f"/api/v1/inquiries/{uuid.uuid4()}")
    assert res_get.status_code == 401


def test_viewer_cannot_submit_or_approve_inquiry(
    test_client: TestClient,
    viewer_headers: dict[str, str],
):
    """Verify that viewer role is forbidden from submitting inquiries or approving drafts."""
    client = test_client

    res_post = client.post(
        "/api/v1/inquiries",
        json={"message": "Inquiry test", "customer": {"first_name": "ViewerTest"}},
        headers=viewer_headers,
    )
    assert res_post.status_code == 403
    assert res_post.json()["error"]["code"] == "FORBIDDEN"

    res_appr = client.post(
        f"/api/v1/inquiries/{uuid.uuid4()}/approve",
        headers=viewer_headers,
    )
    assert res_appr.status_code == 403


def test_inquiry_end_to_end_api_workflow(
    unauthenticated_client_with_db: TestClient,
    agent_headers: dict[str, str],
    viewer_headers: dict[str, str],
):
    """Verify the full HTTP lifecycle: inquiry submission -> draft response -> viewer read -> human approval."""
    client = unauthenticated_client_with_db

    # 1. Submit an inquiry as Agent
    inquiry_payload = {
        "customer": {
            "first_name": "Sophia",
            "last_name": "Loren",
            "email": f"sophia.{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+1 555 987 6543",
        },
        "channel": "WEBSITE",
        "message": "I would like to inquire about customized marble bathtubs for a residential project.",
    }

    res_inquiry = client.post(
        "/api/v1/inquiries",
        json=inquiry_payload,
        headers=agent_headers,
    )
    assert res_inquiry.status_code == 201
    data = res_inquiry.json()

    run_id = data["workflow_run_id"]
    assert data["status"] in ("COMPLETED", "NEEDS_REVIEW")
    assert data["customer_id"] is not None
    assert data["conversation_id"] is not None
    assert data["lead_id"] is not None
    assert data["outbound_message_sent"] is False  # Must NOT be sent without human approval
    assert data["draft"]["approval_status"] == "PENDING_APPROVAL"
    assert len(data["steps"]) >= 6

    # 2. Read inquiry details as Viewer
    res_get = client.get(
        f"/api/v1/inquiries/{run_id}",
        headers=viewer_headers,
    )
    assert res_get.status_code == 200
    get_data = res_get.json()
    assert get_data["workflow_run_id"] == run_id
    assert get_data["draft"]["approval_status"] == "PENDING_APPROVAL"

    # 3. Approve draft as Agent
    res_approve = client.post(
        f"/api/v1/inquiries/{run_id}/approve",
        json={
            "edited_content": "Approved by senior designer: Thank you for your inquiry regarding marble bathtubs."
        },
        headers=agent_headers,
    )
    assert res_approve.status_code == 200
    appr_data = res_approve.json()
    assert appr_data["outbound_message_sent"] is True  # Dispatched after approval
    assert appr_data["draft"]["approval_status"] == "APPROVED"
    assert "Approved by senior designer" in appr_data["draft"]["content"]


def test_inquiry_rejection_api(
    unauthenticated_client_with_db: TestClient,
    agent_headers: dict[str, str],
):
    """Verify that rejecting an inquiry sets its approval status to REJECTED and leaves outbound_sent as False."""
    client = unauthenticated_client_with_db

    inquiry_payload = {
        "customer": {
            "first_name": "Reject",
            "last_name": "Test",
            "email": f"reject.{uuid.uuid4().hex[:6]}@example.com",
        },
        "channel": "WEBSITE",
        "message": "Invalid inquiry test.",
    }

    res_inquiry = client.post(
        "/api/v1/inquiries",
        json=inquiry_payload,
        headers=agent_headers,
    )
    assert res_inquiry.status_code == 201
    run_id = res_inquiry.json()["workflow_run_id"]

    res_reject = client.post(
        f"/api/v1/inquiries/{run_id}/reject",
        json={"reason": "Test rejection reason"},
        headers=agent_headers,
    )
    assert res_reject.status_code == 200
    data = res_reject.json()
    assert data["draft"]["approval_status"] == "REJECTED"
    assert data["outbound_message_sent"] is False
