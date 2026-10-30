"""Unit tests for n8n follow-up integration, approval enforcement, idempotency, retries, and concurrency."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.core.security import WebhookAuthenticationError
from app.db.models.customer import Customer
from app.db.models.enums import Channel, FollowUpStatus, LeadPriority, LeadStatus, MessageDirection
from app.db.models.follow_up import FollowUp
from app.db.models.follow_up_delivery_attempt import FollowUpDeliveryAttempt
from app.db.models.lead import Lead
from app.db.models.message import Message
from app.db.session import SessionLocal
from app.schemas.follow_up import FollowUpCreate, FollowUpUpdate
from app.schemas.n8n_webhook import N8nFollowUpEventRequest
from app.services.follow_up_service import FollowUpService
from app.services.n8n_followup_service import N8nFollowUpService
from pydantic import ValidationError
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
async def test_approval_authorizes_but_does_not_deliver(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 1: Approval authorizes a follow-up; it must not mark it delivered."""
    customer, lead = test_customer_and_lead

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=2),
        reason="Verify crate dimensions for freight elevator access.",
        message_template="Hi Victoria, we have verified elevator clearance.",
    )
    follow_up = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    assert follow_up.approval_status == "PENDING_APPROVAL"
    assert follow_up.delivery_status == "PENDING"
    assert follow_up.status == FollowUpStatus.PENDING.value

    # Approve follow-up
    approved_fu = await FollowUpService.approve_followup(
        db=db_session,
        followup_id=follow_up.id,
        actor_id="manager_david",
        trigger_n8n=False,
    )
    assert approved_fu.approval_status == "APPROVED"
    assert approved_fu.delivery_status == "PENDING"
    assert approved_fu.status == FollowUpStatus.SCHEDULED.value
    assert approved_fu.completed_at is None
    assert approved_fu.conversation_id is None

    # Assert no delivery attempt records were created
    attempts = db_session.query(FollowUpDeliveryAttempt).filter_by(follow_up_id=follow_up.id).all()
    assert len(attempts) == 0


@pytest.mark.asyncio
async def test_future_execution_blocked_without_consuming_attempt(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 2: Future execution is blocked without consuming an attempt."""
    customer, lead = test_customer_and_lead
    future_time = datetime.now(UTC) + timedelta(hours=3)

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=future_time,
        reason="Check on floor loading reinforcement certification.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    req = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:8]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=fu.delivery_id,
        attempt_id=f"att_early_{uuid4().hex[:6]}",
        schedule_version=fu.schedule_version,
        attempt=1,
    )
    res = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)

    assert res.status == "NOT_DUE"
    assert res.delivery_status == "PENDING"
    assert res.retryable is False
    assert res.next_eligible_at is not None
    assert res.delivery_record is None

    # Ensure DB attempt count was not incremented and no attempt row created
    db_session.refresh(fu)
    assert fu.current_attempt == 0
    assert fu.delivery_status == "PENDING"
    assert fu.status == FollowUpStatus.SCHEDULED.value

    attempts = db_session.query(FollowUpDeliveryAttempt).filter_by(follow_up_id=fu.id).all()
    assert len(attempts) == 0


@pytest.mark.asyncio
async def test_due_execution_succeeds_through_mock_sender(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 3: Due execution succeeds through the mock sender."""
    customer, lead = test_customer_and_lead
    past_time = datetime.now(UTC) - timedelta(minutes=5)

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=past_time,
        reason="Follow up on architectural submittal.",
        message_template="Hi Victoria, architectural drawings have been cleared.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    attempt_id = f"att_due_{uuid4().hex[:8]}"
    req = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:8]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=fu.delivery_id,
        attempt_id=attempt_id,
        schedule_version=fu.schedule_version,
        attempt=1,
    )
    res = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)

    assert res.status == "DELIVERED"
    assert res.delivery_status == "DELIVERED"
    assert res.attempt == 1
    assert res.duplicate is False
    assert res.delivery_record is not None
    assert res.delivery_record.provider == "mock"
    assert res.delivery_record.provider_message_id is not None

    db_session.refresh(fu)
    assert fu.status == FollowUpStatus.COMPLETED.value
    assert fu.delivery_status == "DELIVERED"
    assert fu.completed_at is not None
    assert fu.current_attempt == 1
    assert fu.conversation_id is not None

    outbound = (
        db_session.query(Message)
        .filter_by(
            direction=MessageDirection.OUTBOUND.value,
            conversation_id=fu.conversation_id,
        )
        .first()
    )
    assert outbound is not None
    assert "architectural drawings" in outbound.content


def test_unapproved_followup_cannot_execute(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 4a: Unapproved follow-up cannot execute."""
    customer, lead = test_customer_and_lead
    past_time = datetime.now(UTC) - timedelta(minutes=10)

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=past_time,
        reason="Check on deposit schedule.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")

    req = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:8]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=fu.delivery_id,
        attempt_id=f"att_{uuid4().hex[:6]}",
        schedule_version=fu.schedule_version,
    )
    res = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)

    assert res.status == "UNAPPROVED"
    assert res.delivery_status == "PENDING"
    assert res.delivery_record is None

    db_session.refresh(fu)
    assert fu.status == FollowUpStatus.PENDING.value
    assert fu.completed_at is None


@pytest.mark.asyncio
async def test_cancelled_followup_cannot_execute(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 4b: Cancelled follow-up cannot execute."""
    customer, lead = test_customer_and_lead
    past_time = datetime.now(UTC) - timedelta(minutes=10)

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=past_time,
        reason="Follow up on site survey.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    FollowUpService.cancel_followup(
        db=db_session,
        followup_id=fu.id,
        reason="Client postponed renovation project indefinitely.",
    )

    req = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:8]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=fu.delivery_id,
        attempt_id=f"att_{uuid4().hex[:6]}",
        schedule_version=fu.schedule_version,
    )
    res = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)

    assert res.status == "CANCELLED"
    assert res.delivery_status == "CANCELLED"
    assert res.delivery_record is None


@pytest.mark.asyncio
async def test_rescheduled_followup_rejects_stale_queued_executions(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 5: Rescheduled follow-up rejects stale queued executions."""
    customer, lead = test_customer_and_lead
    initial_time = datetime.now(UTC) - timedelta(minutes=5)

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=initial_time,
        reason="Initial delivery window check.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    old_delivery_id = fu.delivery_id
    old_schedule_version = fu.schedule_version
    assert old_schedule_version == 1

    # Client reschedules follow-up to tomorrow
    new_time = datetime.now(UTC) + timedelta(days=1)
    rescheduled_fu = FollowUpService.update_followup(
        db=db_session,
        followup_id=fu.id,
        updates=FollowUpUpdate(scheduled_at=new_time),
        actor_id="agent",
    )
    assert rescheduled_fu.schedule_version == 2
    assert rescheduled_fu.delivery_id != old_delivery_id

    # Older n8n queued execution wakes up with stale version / delivery_id
    stale_req = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:8]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=old_delivery_id,
        attempt_id=f"att_stale_{uuid4().hex[:6]}",
        schedule_version=old_schedule_version,
        attempt=1,
    )
    res = N8nFollowUpService.process_event(db_session, stale_req, secret_header=SECRET)

    assert res.status == "STALE_SCHEDULE"
    assert res.retryable is False
    assert res.delivery_record is None

    # Assert no delivery happened
    db_session.refresh(fu)
    assert fu.status == FollowUpStatus.SCHEDULED.value
    assert fu.delivery_status == "PENDING"
    assert fu.completed_at is None


@pytest.mark.asyncio
async def test_replaying_attempt_id_does_not_send_again(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 6: Replaying an attempt returns recorded outcome without duplicate send."""
    customer, lead = test_customer_and_lead
    past_time = datetime.now(UTC) - timedelta(minutes=5)

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=past_time,
        reason="Send marble sample tracking link.",
        message_template="Your samples have shipped.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    attempt_id = f"att_replay_{uuid4().hex[:8]}"
    req = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:8]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=fu.delivery_id,
        attempt_id=attempt_id,
        schedule_version=fu.schedule_version,
        attempt=1,
    )

    # First dispatch -> DELIVERED
    res1 = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)
    assert res1.status == "DELIVERED"
    assert res1.duplicate is False
    assert res1.delivery_record is not None
    original_msg_id = res1.delivery_record.provider_message_id

    # Second dispatch with identical attempt_id -> DUPLICATE_REPLAY
    res2 = N8nFollowUpService.process_event(db_session, req, secret_header=SECRET)
    assert res2.status == "DUPLICATE_REPLAY"
    assert res2.duplicate is True
    assert res2.delivery_record is not None
    assert res2.delivery_record.provider_message_id == original_msg_id

    # Assert only 1 outbound message created in conversation
    db_session.refresh(fu)
    messages = (
        db_session.query(Message)
        .filter_by(
            direction=MessageDirection.OUTBOUND.value,
            conversation_id=fu.conversation_id,
        )
        .all()
    )
    assert len(messages) == 1

    # Assert only 1 delivery attempt recorded in database
    attempts = db_session.query(FollowUpDeliveryAttempt).filter_by(follow_up_id=fu.id).all()
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_completed_followup_rejects_new_attempts(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 6b: Completed follow-up rejects execution attempts with new attempt_ids."""
    customer, lead = test_customer_and_lead
    past_time = datetime.now(UTC) - timedelta(minutes=5)

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=past_time,
        reason="Initial quote follow-up.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    # Complete it first with attempt 1
    req1 = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=fu.delivery_id,
        attempt_id=f"att_first_{uuid4().hex[:6]}",
        schedule_version=fu.schedule_version,
        attempt=1,
    )
    res1 = N8nFollowUpService.process_event(db_session, req1, secret_header=SECRET)
    assert res1.status == "DELIVERED"

    # Attempt send with different attempt_id and attempt number
    req2 = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=fu.delivery_id,
        attempt_id=f"att_second_{uuid4().hex[:6]}",
        schedule_version=fu.schedule_version,
        attempt=2,
    )
    res2 = N8nFollowUpService.process_event(db_session, req2, secret_header=SECRET)
    assert res2.status == "ALREADY_COMPLETED"
    assert res2.duplicate is True

    attempts = db_session.query(FollowUpDeliveryAttempt).filter_by(follow_up_id=fu.id).all()
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_retryable_failure_and_bounded_retry_exhaustion(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 7 & 8: Retryable failure permits next attempt; max retry exhaustion is terminal."""
    customer, lead = test_customer_and_lead
    past_time = datetime.now(UTC) - timedelta(minutes=5)

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=past_time,
        reason="Confirm crate delivery schedule.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    delivery_id = fu.delivery_id
    sched_ver = fu.schedule_version
    max_retries = 3

    # Attempt 1 -> RETRYING
    req1 = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=delivery_id,
        attempt_id=f"att_1_{uuid4().hex[:6]}",
        schedule_version=sched_ver,
        attempt=1,
        max_retries=max_retries,
        payload={"simulate_failure": True, "simulate_error": "Connection reset by peer"},
    )
    res1 = N8nFollowUpService.process_event(db_session, req1, secret_header=SECRET)
    assert res1.status == "RETRYING"
    assert res1.retryable is True
    assert res1.delivery_status == "RETRYING"
    assert res1.attempt == 1

    db_session.refresh(fu)
    assert fu.status == FollowUpStatus.PROCESSING.value
    assert fu.current_attempt == 1

    # Attempt 2 -> RETRYING
    req2 = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=delivery_id,
        attempt_id=f"att_2_{uuid4().hex[:6]}",
        schedule_version=sched_ver,
        attempt=2,
        max_retries=max_retries,
        payload={"simulate_failure": True, "simulate_error": "Timeout connecting to gateway"},
    )
    res2 = N8nFollowUpService.process_event(db_session, req2, secret_header=SECRET)
    assert res2.status == "RETRYING"
    assert res2.retryable is True
    assert res2.attempt == 2

    # Attempt 3 -> FAILED (Terminal exhaustion at max_retries=3)
    req3 = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=delivery_id,
        attempt_id=f"att_3_{uuid4().hex[:6]}",
        schedule_version=sched_ver,
        attempt=3,
        max_retries=max_retries,
        payload={"simulate_failure": True, "simulate_error": "Gateway unavailable"},
    )
    res3 = N8nFollowUpService.process_event(db_session, req3, secret_header=SECRET)
    assert res3.status == "FAILED"
    assert res3.retryable is False
    assert res3.delivery_status == "FAILED"
    assert res3.attempt == 3

    # Assert visible delivery records
    deliv = FollowUpService.get_delivery_status(db_session, fu.id)
    assert deliv.status == FollowUpStatus.FAILED.value
    assert deliv.delivery_status == "FAILED"
    assert len(deliv.delivery_records) == 3
    assert "Max retries (3) exhausted" in deliv.failure_reason


@pytest.mark.asyncio
async def test_retryable_failure_permits_subsequent_successful_attempt(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 7b: After a retryable failure, next legitimate attempt succeeds."""
    customer, lead = test_customer_and_lead
    past_time = datetime.now(UTC) - timedelta(minutes=5)

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=past_time,
        reason="Follow up on custom vanity quotation.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")
    await FollowUpService.approve_followup(db_session, fu.id, actor_id="manager", trigger_n8n=False)

    delivery_id = fu.delivery_id
    sched_ver = fu.schedule_version

    # Attempt 1 fails transiently
    req1 = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=delivery_id,
        attempt_id=f"att_fail_{uuid4().hex[:6]}",
        schedule_version=sched_ver,
        attempt=1,
        max_retries=3,
        payload={"simulate_failure": True, "simulate_error": "Temporary network hiccup"},
    )
    res1 = N8nFollowUpService.process_event(db_session, req1, secret_header=SECRET)
    assert res1.status == "RETRYING"

    # Attempt 2 succeeds
    req2 = N8nFollowUpEventRequest(
        event_id=f"evt_{uuid4().hex[:6]}",
        event_type="followup.execute",
        followup_id=fu.id,
        delivery_id=delivery_id,
        attempt_id=f"att_success_{uuid4().hex[:6]}",
        schedule_version=sched_ver,
        attempt=2,
        max_retries=3,
    )
    res2 = N8nFollowUpService.process_event(db_session, req2, secret_header=SECRET)
    assert res2.status == "DELIVERED"
    assert res2.delivery_status == "DELIVERED"
    assert res2.attempt == 2

    # Assert 2 attempts in database
    attempts = (
        db_session.query(FollowUpDeliveryAttempt)
        .filter_by(follow_up_id=fu.id)
        .order_by(FollowUpDeliveryAttempt.attempt.asc())
        .all()
    )
    assert len(attempts) == 2
    assert attempts[0].status == "FAILED"
    assert attempts[1].status == "DELIVERED"


def test_timezone_validation_rejects_naive_and_normalizes():
    """Verify that scheduled_at rejects timezone-naive inputs and normalizes timezone offsets."""
    # 1. Naive datetime raises ValidationError
    naive_dt = datetime(2026, 11, 15, 14, 30, 0)
    with pytest.raises(ValidationError) as exc1:
        FollowUpCreate(
            lead_id="lead_1",
            customer_id="cust_1",
            channel=Channel.WHATSAPP,
            scheduled_at=naive_dt,
            reason="Check specifications.",
        )
    assert "scheduled_at must include an explicit timezone offset" in str(exc1.value)

    # 2. Naive datetime in FollowUpUpdate raises ValidationError
    with pytest.raises(ValidationError) as exc2:
        FollowUpUpdate(scheduled_at=naive_dt)
    assert "scheduled_at must include an explicit timezone offset" in str(exc2.value)

    # 3. Explicit timezone is accepted and normalized to UTC
    tz_aware = datetime.now(UTC)
    fu_in = FollowUpCreate(
        lead_id="lead_1",
        customer_id="cust_1",
        channel=Channel.WHATSAPP,
        scheduled_at=tz_aware,
        reason="Check specifications.",
    )
    assert fu_in.scheduled_at.tzinfo == UTC


def test_protected_metadata_keys_stripped(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario: Protected workflow keys cannot be injected via client metadata."""
    customer, lead = test_customer_and_lead

    # Attempt to bypass workflow state by injecting protected keys into metadata
    malicious_meta = {
        "approval_status": "APPROVED",
        "delivery_status": "DELIVERED",
        "current_attempt": 99,
        "schedule_version": 42,
        "delivery_id": "fake_delivery_id",
        "customer_tag": "vip_architect",
    }
    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        reason="Check VIP inquiry.",
        metadata=malicious_meta,
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")

    # Protected keys must be stripped from metadata
    assert "approval_status" not in fu.metadata_
    assert "delivery_status" not in fu.metadata_
    assert "current_attempt" not in fu.metadata_
    assert "schedule_version" not in fu.metadata_
    assert "delivery_id" not in fu.metadata_
    # Legitimate custom metadata is preserved
    assert fu.metadata_["customer_tag"] == "vip_architect"

    # Backend columns remain accurately set
    assert fu.approval_status == "PENDING_APPROVAL"
    assert fu.delivery_status == "PENDING"
    assert fu.current_attempt == 0
    assert fu.schedule_version == 1
    assert fu.delivery_id is not None


@pytest.mark.asyncio
async def test_failed_real_n8n_dispatch_visibility_and_retry(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 10: Failed real n8n dispatch remains visible and can be retried safely."""
    from app.core.exceptions import ExternalServiceException

    customer, lead = test_customer_and_lead

    fu_in = FollowUpCreate(
        lead_id=lead.id,
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        reason="Follow up on bathtub quote.",
    )
    fu = FollowUpService.schedule_followup(db_session, fu_in, actor_id="agent")

    # Simulate dispatch failure in n8n client using AsyncMock
    mock_instance = MagicMock()
    mock_instance.trigger_workflow = AsyncMock(
        side_effect=ExternalServiceException(
            message="n8n server unreachable: connection refused",
            details={"service": "n8n"},
        )
    )

    with patch("app.services.follow_up_service.N8nWebhookClient", return_value=mock_instance):
        approved_fu = await FollowUpService.approve_followup(
            db=db_session,
            followup_id=fu.id,
            actor_id="manager",
            trigger_n8n=True,
        )

    # Approved, but dispatch failure recorded
    assert approved_fu.approval_status == "APPROVED"
    assert approved_fu.n8n_dispatch_status == "FAILED"
    assert "n8n server unreachable" in approved_fu.n8n_dispatch_error
    orig_delivery_id = approved_fu.delivery_id

    # Now simulate retry succeeding
    mock_instance.trigger_workflow = AsyncMock(return_value={"status": "dispatched", "mock": False})

    with patch("app.services.follow_up_service.N8nWebhookClient", return_value=mock_instance):
        retried_fu = await FollowUpService.dispatch_followup_to_n8n(
            db=db_session,
            followup_id=fu.id,
            actor_id="manager",
        )

    assert retried_fu.n8n_dispatch_status == "DISPATCHED"
    assert retried_fu.n8n_dispatch_error is None
    # Crucial: delivery_id is preserved so duplicate logical deliveries are not created
    assert retried_fu.delivery_id == orig_delivery_id


def test_concurrent_duplicate_requests_result_in_one_claimed_execution(
    setup_test_database: bool,
):
    """Scenario 9: Concurrent duplicate requests result in exactly one claimed execution."""
    if not setup_test_database:
        pytest.skip("PostgreSQL test database required for concurrency tests.")

    # Use distinct sessions from SessionLocal to simulate true concurrent clients
    db_setup = SessionLocal()
    try:
        customer = Customer(
            first_name="Concur",
            last_name="Test",
            email=f"concur.{uuid4().hex[:6]}@example.com",
            phone=f"+1415555{uuid4().hex[:4]}",
            source="WEBSITE",
        )
        db_setup.add(customer)
        db_setup.flush()

        lead = Lead(
            customer_id=customer.id,
            interest_description="Concurrency verification tub",
            status=LeadStatus.QUALIFIED.value,
            priority=LeadPriority.HIGH.value,
        )
        db_setup.add(lead)
        db_setup.commit()

        fu_in = FollowUpCreate(
            lead_id=lead.id,
            customer_id=customer.id,
            channel=Channel.WHATSAPP,
            scheduled_at=datetime.now(UTC) - timedelta(minutes=5),
            reason="Concurrent delivery test.",
            message_template="Hi Concur, this should only be delivered once.",
        )
        fu = FollowUpService.schedule_followup(db_setup, fu_in, actor_id="agent")
        fu.approval_status = "APPROVED"
        fu.status = FollowUpStatus.SCHEDULED.value
        db_setup.commit()

        followup_id = fu.id
        delivery_id = fu.delivery_id
        sched_ver = fu.schedule_version

        def execute_webhook_request(attempt_id: str):
            session = SessionLocal()
            try:
                req = N8nFollowUpEventRequest(
                    event_id=f"evt_{uuid4().hex[:8]}",
                    event_type="followup.execute",
                    followup_id=followup_id,
                    delivery_id=delivery_id,
                    attempt_id=attempt_id,
                    schedule_version=sched_ver,
                    attempt=1,
                )
                res = N8nFollowUpService.process_event(session, req, secret_header=SECRET)
                return res.status
            finally:
                session.close()

        # Fire two concurrent calls with the same attempt_id (concurrent duplicate replay / execution)
        shared_attempt_id = f"att_race_{uuid4().hex[:8]}"
        with ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(execute_webhook_request, shared_attempt_id)
            future2 = executor.submit(execute_webhook_request, shared_attempt_id)
            status1 = future1.result()
            status2 = future2.result()

        statuses = [status1, status2]
        # One must be DELIVERED, and the other must be DUPLICATE_REPLAY (or ALREADY_COMPLETED/CLAIM_ACTIVE)
        assert "DELIVERED" in statuses
        assert (
            "DUPLICATE_REPLAY" in statuses
            or "ALREADY_COMPLETED" in statuses
            or "CLAIM_ACTIVE" in statuses
        )

        # Confirm exactly 1 delivery attempt recorded and 1 message delivered
        attempts = db_setup.query(FollowUpDeliveryAttempt).filter_by(follow_up_id=followup_id).all()
        assert len(attempts) == 1

        db_setup.refresh(fu)
        messages = (
            db_setup.query(Message)
            .filter_by(
                direction=MessageDirection.OUTBOUND.value,
                conversation_id=fu.conversation_id,
            )
            .all()
        )
        assert len(messages) == 1

    finally:
        db_setup.close()


def test_webhook_authentication_failure(
    db_session: Session, test_customer_and_lead: tuple[Customer, Lead]
):
    """Scenario 11: Webhook authentication failure."""
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
