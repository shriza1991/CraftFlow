"""Unit tests for n8n follow-up integration, approval enforcement, idempotency, and retries."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.core.security import WebhookAuthenticationError
from app.db.models.customer import Customer
from app.db.models.enums import Channel, FollowUpStatus, LeadPriority, LeadStatus, MessageDirection
from app.db.models.follow_up import FollowUp
from app.db.models.lead import Lead
from app.db.models.message import Message
from app.schemas.follow_up import FollowUpCreate
from app.schemas.n8n_webhook import N8nFollowUpEventRequest
from app.services.follow_up_service import FollowUpService
from app.services.n8n_followup_service import N8nFollowUpService
from sqlalchemy.orm import Session

settings = get_settings()
SECRET = settings.N8N_WEBHOOK_SECRET


@pytest.fixture
def test_customer_and_lead(db_session: Session) -> tuple[Customer, Lead]:
    """Helper fixture creating customer and lead for testing."""
    customer = Customer(
        first_name="Victoria",
        last_name="Sterling",
        email=f"victoria.{uuid4().hex[:6]}@example.com",
        phone=f"+1415555{uuid4().hex[:4]}",
        source="WEBSITE",
    )
    db_session.add(customer)
    db_session.flush()

    lead = Lead(
        customer_id=customer.id,
        interest_description="Penthouse custom soaking tub inquiry",
        status=LeadStatus.QUALIFIED.value,
        priority=LeadPriority.HIGH.value,
        estimated_value=22000.00,
    )
    db_session.add(lead)
    db_session.commit()
    return customer, lead


@pytest.mark.asyncio
async def test_approved_followup_moves_through_n8n_workflow(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Verify that an approved follow-up moves through n8n delivery and updates records."""
    customer, lead = test_customer_and_lead

    # 1. Schedule follow-up (pending approval)
    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=2),
        reason="Verify crate dimensions for freight elevator access.",
        message_template="Hi Victoria, we have verified the elevator clearance for your tub delivery.",
    )
    follow_up = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    assert follow_up.metadata_.get("approval_status") == "PENDING_APPROVAL"

    # 2. Human approval action
    approved_fu = await FollowUpService.approve_followup(
        db=db_session,
        followup_id=follow_up.id,
        actor_id="manager_david",
        trigger_n8n=False,
    )
    assert approved_fu.metadata_.get("approval_status") == "APPROVED"
    assert approved_fu.status == FollowUpStatus.SCHEDULED.value

    # 3. n8n executes webhook
    event_id = f"evt_{uuid4().hex[:12]}"
    req = N8nFollowUpEventRequest(
        event_id=event_id,
        event_type="followup.execute",
        followup_id=approved_fu.id,
        attempt=1,
        max_retries=3,
    )
    res = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)

    # 4. Assert delivery outcome
    assert res.status == "DELIVERED"
    assert res.delivery_status == "DELIVERED"
    assert res.attempt == 1
    assert res.duplicate is False
    assert res.delivery_record is not None
    assert res.delivery_record.provider_message_id is not None

    # 5. Assert database records
    db_session.refresh(follow_up)
    assert follow_up.status == FollowUpStatus.COMPLETED.value
    assert follow_up.completed_at is not None
    assert follow_up.metadata_["delivery_status"] == "DELIVERED"
    assert len(follow_up.metadata_["delivery_records"]) == 1

    # 6. Assert outbound message record created in conversation
    outbound_msg = (
        db_session.query(Message).filter_by(direction=MessageDirection.OUTBOUND.value).first()
    )
    assert outbound_msg is not None
    assert "Hi Victoria" in outbound_msg.content


def test_unapproved_followup_rejected(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Verify that an unapproved follow-up cannot be delivered."""
    customer, lead = test_customer_and_lead

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=3),
        reason="Check on deposit schedule.",
    )
    follow_up = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")

    req = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:12]}",
        event_type="followup.execute",
        followup_id=follow_up.id,
    )
    res = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)

    assert res.status == "UNAPPROVED"
    assert res.delivery_status == "PENDING_APPROVAL"
    assert res.delivery_record is None

    db_session.refresh(follow_up)
    assert follow_up.status == FollowUpStatus.PENDING.value
    assert follow_up.completed_at is None


@pytest.mark.asyncio
async def test_repeated_event_id_duplicate_protection(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Verify that repeating an event ID is idempotent and causes zero duplicate sends."""
    customer, lead = test_customer_and_lead

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        reason="Send marble sample tracking link.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    event_id = f"evt_idempotent_{uuid4().hex[:8]}"
    req = N8nFollowUpEventRequest(
        event_id=event_id,
        event_type="followup.execute",
        followup_id=fu.id,
    )

    # First dispatch -> SUCCESS
    res1 = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)
    assert res1.status == "DELIVERED"
    assert res1.duplicate is False

    # Second dispatch with identical event_id -> DUPLICATE_IGNORED
    res2 = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)
    assert res2.status == "DUPLICATE_IGNORED"
    assert res2.duplicate is True

    # Assert exactly 1 delivery record in database
    deliv_status = FollowUpService.get_delivery_status(db_session, fu.id)
    assert len(deliv_status.delivery_records) == 1


@pytest.mark.asyncio
async def test_completed_followup_rejects_duplicate_sends(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Verify that a completed follow-up cannot be sent again with a new event ID."""
    customer, lead = test_customer_and_lead

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        reason="Initial quote follow-up.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    # Complete it first
    req1 = N8nFollowUpEventRequest(
        event_id=f"evt_first_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
    )
    res1 = N8nFollowUpService.process_event(db_session, req1, secret_header=SECRET)
    assert res1.status == "DELIVERED"

    # Now attempt a send with a different event ID
    req2 = N8nFollowUpEventRequest(
        event_id=f"evt_second_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
    )
    res2 = N8nFollowUpService.process_event(db_session, req2, secret_header=SECRET)
    assert res2.status == "ALREADY_COMPLETED"
    assert res2.duplicate is True

    deliv_status = FollowUpService.get_delivery_status(db_session, fu.id)
    assert len(deliv_status.delivery_records) == 1


@pytest.mark.asyncio
async def test_cancelled_followup_rejected(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Verify that cancelled follow-ups cannot be dispatched."""
    customer, lead = test_customer_and_lead

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=4),
        reason="Follow-up on site survey.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    # Cancel follow-up
    FollowUpService.cancel_followup(
        db=db_session,
        followup_id=fu.id,
        reason="Client postponed renovation project indefinitely.",
    )

    req = N8nFollowUpEventRequest(
        event_id=f"evt_cancelled_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
    )
    res = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)

    assert res.status == "CANCELLED"
    assert res.delivery_status == "CANCELLED"
    assert res.delivery_record is None


@pytest.mark.asyncio
async def test_delivery_failure_and_bounded_retry_exhaustion(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Verify retry progression and bounded failure handling when max retries are exceeded."""
    customer, lead = test_customer_and_lead

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=2),
        reason="Confirm crate delivery schedule.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    max_retries = 3

    # Attempt 1 -> RETRYING
    req1 = N8nFollowUpEventRequest(
        event_id=f"evt_att_1_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        attempt=1,
        max_retries=max_retries,
        payload={"simulate_failure": True, "simulate_error": "Connection reset by peer"},
    )
    res1 = N8nFollowUpService.process_event(db_session, req1, secret_header=SECRET)
    assert res1.status == "RETRYING"
    assert res1.retryable is True
    assert res1.delivery_status == "RETRYING"

    db_session.refresh(fu)
    assert fu.status == FollowUpStatus.PROCESSING.value

    # Attempt 2 -> RETRYING
    req2 = N8nFollowUpEventRequest(
        event_id=f"evt_att_2_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        attempt=2,
        max_retries=max_retries,
        payload={"simulate_failure": True, "simulate_error": "Timeout connecting to gateway"},
    )
    res2 = N8nFollowUpService.process_event(db_session, req2, secret_header=SECRET)
    assert res2.status == "RETRYING"
    assert res2.retryable is True

    # Attempt 3 -> FAILED (Max retries exhausted!)
    req3 = N8nFollowUpEventRequest(
        event_id=f"evt_att_3_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        attempt=3,
        max_retries=max_retries,
        payload={"simulate_failure": True, "simulate_error": "Gateway unavailable"},
    )
    res3 = N8nFollowUpService.process_event(db_session, req3, secret_header=SECRET)
    assert res3.status == "FAILED"
    assert res3.retryable is False
    assert res3.delivery_status == "FAILED"

    # Assert visible delivery records
    deliv = FollowUpService.get_delivery_status(db_session, fu.id)
    assert deliv.status == FollowUpStatus.FAILED.value
    assert len(deliv.delivery_records) == 3
    assert "Max retries (3) exhausted" in deliv.failure_reason


def test_webhook_authentication_failure(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Verify that webhooks with invalid or missing secrets are rejected."""
    _customer, lead = test_customer_and_lead

    req = N8nFollowUpEventRequest(
        event_id="evt_unauth",
        event_type="followup.execute",
        followup_id=lead.id,
    )

    with pytest.raises(WebhookAuthenticationError):
        N8nFollowUpService.process_event(db_session, req, secret_header="wrong_secret")

    with pytest.raises(WebhookAuthenticationError):
        N8nFollowUpService.process_event(db_session, req, secret_header=None)


def test_schedule_followup_deduplication(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Verify that repeated schedule events do not create duplicate follow-up records."""
    customer, lead = test_customer_and_lead
    scheduled_time = (datetime.now(UTC) + timedelta(days=5)).isoformat()

    event_id = f"evt_sched_{uuid4().hex[:8]}"
    req = N8nFollowUpEventRequest(
        event_id=event_id,
        event_type="followup.schedule",
        followup_id="placeholder",
        payload={
            "lead_id": lead.id,
            "customer_id": customer.id,
            "scheduled_at": scheduled_time,
            "reason": "Scheduled check-in via n8n workflow",
        },
    )

    # First event creates follow-up
    res1 = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)
    assert res1.duplicate is False
    followup_id = res1.followup_id

    # Re-sending same event returns DUPLICATE_IGNORED and same follow-up ID
    res2 = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)
    assert res2.status == "DUPLICATE_IGNORED"
    assert res2.duplicate is True
    assert res2.followup_id == followup_id

    # Verify only 1 follow-up exists for this lead
    all_fus = db_session.query(FollowUp).filter_by(lead_id=lead.id).all()
    assert len(all_fus) == 1
