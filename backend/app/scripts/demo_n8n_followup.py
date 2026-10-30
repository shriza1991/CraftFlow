# ruff: noqa: E402
"""Standalone demo script for CraftFlow n8n integration with approved follow-ups.

Demonstrates:
  1. Early execution rejection (future follow-ups return NOT_DUE without consuming attempts).
  2. Approved, due follow-up moving through n8n automation and mock messaging delivery.
  3. Replay of same attempt returning cached DUPLICATE_REPLAY outcome without re-sending.
  4. Rescheduling invalidating older queued executions (STALE_SCHEDULE rejection).
  5. Transient failure handling, retry progression, and bounded failure exhaustion (max retries).
  6. Cancelled follow-up rejection (cancelled touchpoints are not dispatched).
  7. Unapproved follow-up protection (enforcing backend human approval gate).
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings
from app.db.models.customer import Customer
from app.db.models.enums import ActorType, Channel, LeadPriority, LeadStatus
from app.db.models.lead import Lead
from app.db.session import SessionLocal, engine
from app.schemas.follow_up import FollowUpCreate, FollowUpUpdate
from app.schemas.n8n_webhook import N8nFollowUpEventRequest
from app.services.follow_up_service import FollowUpService
from app.services.n8n_followup_service import N8nFollowUpService

# Silence verbose SQLAlchemy query logging for clean demo output
engine.echo = False
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

settings = get_settings()
SECRET = settings.N8N_WEBHOOK_SECRET


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_step(title: str) -> None:
    print("\n" + "-" * 80)
    print(f">>> {title}")
    print("-" * 80)


async def main() -> None:
    print_header("CraftFlow n8n Follow-up Automation Demo (Mock Provider)")
    db = SessionLocal()

    try:
        # Create base test customer and lead
        suffix = uuid4().hex[:6]
        customer = Customer(
            first_name="Alexander",
            last_name="Wright",
            email=f"alexander.{suffix}@example.com",
            phone=f"+1415555{suffix[:4]}",
            source="WEBSITE",
        )
        db.add(customer)
        db.flush()

        lead = Lead(
            customer_id=customer.id,
            interest_description="Master Suite Stone Bath Installation",
            status=LeadStatus.QUALIFIED.value,
            priority=LeadPriority.HIGH.value,
            estimated_value=18500.00,
        )
        db.add(lead)
        db.commit()

        # ----------------------------------------------------------------------
        # SCENARIO 1: Early Execution Rejection (Not Due Yet)
        # ----------------------------------------------------------------------
        print_step("SCENARIO 1: Early Execution Rejection (Not Due Yet)")

        future_time = datetime.now(UTC) + timedelta(days=2)
        fu_create = FollowUpCreate(
            lead_id=lead.id,
            customer_id=customer.id,
            channel=Channel.WHATSAPP,
            scheduled_at=future_time,
            reason="Confirm quarry slab inspection and delivery timeline.",
            message_template="Hi Alexander, our artisan team completed the block inspection for your tub.",
        )
        follow_up = FollowUpService.schedule_followup(
            db=db,
            followup_in=fu_create,
            actor_id="sales_agent_rachel",
            actor_type=ActorType.HUMAN,
        )
        await FollowUpService.approve_followup(
            db=db,
            followup_id=follow_up.id,
            actor_id="sales_manager_david",
            trigger_n8n=False,
        )
        print(
            f"Follow-up Scheduled : {follow_up.id} (Scheduled at: {follow_up.scheduled_at.isoformat()})"
        )
        print(f"Approval Result     : {follow_up.approval_status}")

        early_req = N8nFollowUpEventRequest(
            delivery_id=follow_up.delivery_id,
            attempt_id=f"att_early_{uuid4().hex[:8]}",
            event_type="followup.execute",
            followup_id=follow_up.id,
            schedule_version=follow_up.schedule_version,
            attempt=1,
        )
        print("\n[n8n Webhook Relay] Executing prematurely before due time...")
        early_res = N8nFollowUpService.process_event(
            db=db, event_data=early_req, secret_header=SECRET
        )
        print(f"Relay Response Status : {early_res.status} (Expected: NOT_DUE)")
        print(f"Next Eligible At      : {early_res.next_eligible_at}")
        print(f"Attempts Consumed     : {follow_up.current_attempt} (Expected: 0)")

        # ----------------------------------------------------------------------
        # SCENARIO 2: Due Execution & Replay Idempotency
        # ----------------------------------------------------------------------
        print_step("SCENARIO 2: Due Follow-up Execution & Replay Idempotency")

        # Reschedule follow-up to now (due)
        now_time = datetime.now(UTC) - timedelta(seconds=5)
        FollowUpService.update_followup(
            db=db,
            followup_id=follow_up.id,
            updates=FollowUpUpdate(scheduled_at=now_time),
        )
        db.refresh(follow_up)
        print(
            f"Follow-up Rescheduled to Due Time: {follow_up.scheduled_at.isoformat()} (Version: {follow_up.schedule_version})"
        )

        due_attempt_id = f"att_1_{follow_up.delivery_id}"
        due_req = N8nFollowUpEventRequest(
            delivery_id=follow_up.delivery_id,
            attempt_id=due_attempt_id,
            event_type="followup.execute",
            followup_id=follow_up.id,
            schedule_version=follow_up.schedule_version,
            attempt=1,
            max_retries=3,
        )
        print(
            f"\n[n8n Webhook Relay] Dispatching due execution (delivery_id='{follow_up.delivery_id}')..."
        )
        res1 = N8nFollowUpService.process_event(db=db, event_data=due_req, secret_header=SECRET)
        print(f"Relay Response Status : {res1.status} (Expected: DELIVERED)")
        print(f"Delivery Status       : {res1.delivery_status}")
        print(
            f"Provider Message ID   : {res1.delivery_record.provider_message_id if res1.delivery_record else 'N/A'}"
        )

        # Replay identical attempt
        print(f"\n[n8n Replay] Re-sending identical attempt '{due_attempt_id}'...")
        res_replay = N8nFollowUpService.process_event(
            db=db, event_data=due_req, secret_header=SECRET
        )
        print(f"Relay Response Status : {res_replay.status} (Duplicate: {res_replay.duplicate})")
        print(f"Message               : {res_replay.message}")

        deliv_status = FollowUpService.get_delivery_status(db, follow_up.id)
        print(
            f"Recorded Delivery Records in DB: {len(deliv_status.delivery_records)} (Expected: exactly 1)"
        )

        # ----------------------------------------------------------------------
        # SCENARIO 3: Rescheduled Follow-up Invalidation (Stale Execution Rejection)
        # ----------------------------------------------------------------------
        print_step("SCENARIO 3: Rescheduling Invalidates Stale Queued Executions")
        fu_resched_create = FollowUpCreate(
            lead_id=lead.id,
            customer_id=customer.id,
            channel=Channel.WHATSAPP,
            scheduled_at=datetime.now(UTC) + timedelta(days=1),
            reason="Coordinate crane arrival and street permit.",
        )
        fu_resched = FollowUpService.schedule_followup(db=db, followup_in=fu_resched_create)
        await FollowUpService.approve_followup(db=db, followup_id=fu_resched.id, trigger_n8n=False)
        old_delivery_id = fu_resched.delivery_id
        old_version = fu_resched.schedule_version
        print(
            f"Created Follow-up: {fu_resched.id} (Version: {old_version}, Delivery ID: {old_delivery_id})"
        )

        print("[User Action] Client requested postponing by one week...")
        FollowUpService.update_followup(
            db=db,
            followup_id=fu_resched.id,
            updates=FollowUpUpdate(scheduled_at=datetime.now(UTC) + timedelta(days=8)),
        )
        db.refresh(fu_resched)
        print(
            f"Rescheduled Follow-up: new version {fu_resched.schedule_version}, new delivery_id '{fu_resched.delivery_id}'"
        )

        print("\n[n8n Relay] Stale execution queued before reschedule attempts to execute...")
        stale_req = N8nFollowUpEventRequest(
            delivery_id=old_delivery_id,
            attempt_id=f"att_stale_{uuid4().hex[:6]}",
            event_type="followup.execute",
            followup_id=fu_resched.id,
            schedule_version=old_version,
            attempt=1,
        )
        res_stale = N8nFollowUpService.process_event(
            db=db, event_data=stale_req, secret_header=SECRET
        )
        print(f"Relay Response Status : {res_stale.status} (Expected: STALE_SCHEDULE)")
        print(f"Message               : {res_stale.message}")

        # ----------------------------------------------------------------------
        # SCENARIO 4: Delivery Failure, Retry Progression, & Bounded Exhaustion
        # ----------------------------------------------------------------------
        print_step("SCENARIO 4: Failure Handling, Retries, & Bounded Exhaustion (Max 3)")
        fu_retry_create = FollowUpCreate(
            lead_id=lead.id,
            customer_id=customer.id,
            channel=Channel.WHATSAPP,
            scheduled_at=datetime.now(UTC) - timedelta(minutes=1),  # Due now
            reason="Verify final crating and air-freight booking.",
        )
        fu_retry = FollowUpService.schedule_followup(db=db, followup_in=fu_retry_create)
        await FollowUpService.approve_followup(db=db, followup_id=fu_retry.id, trigger_n8n=False)

        for attempt in range(1, 4):
            att_id = f"att_{attempt}_{fu_retry.delivery_id}_{uuid4().hex[:6]}"
            req = N8nFollowUpEventRequest(
                delivery_id=fu_retry.delivery_id,
                attempt_id=att_id,
                event_type="followup.execute",
                followup_id=fu_retry.id,
                schedule_version=fu_retry.schedule_version,
                attempt=attempt,
                max_retries=3,
                payload={
                    "simulate_failure": True,
                    "simulate_error": "Carrier network gateway timeout (HTTP 504)",
                },
            )
            print(f"\n[n8n Relay Attempt {attempt}/3] Dispatching attempt '{att_id}'...")
            res_retry = N8nFollowUpService.process_event(
                db=db, event_data=req, secret_header=SECRET
            )
            print(f"  Attempt Status : {res_retry.status} (Retryable: {res_retry.retryable})")
            print(f"  CRM Status     : {res_retry.delivery_status}")
            print(f"  Message        : {res_retry.message}")

        deliv_retry = FollowUpService.get_delivery_status(db, fu_retry.id)
        print("\nFinal State after Max Retries:")
        print(f"  Overall Status : {deliv_retry.status} (Expected: FAILED)")
        print(f"  Failure Reason : {deliv_retry.failure_reason}")
        print(f"  Total Attempts : {len(deliv_retry.delivery_records)} / {deliv_retry.max_retries}")

        # ----------------------------------------------------------------------
        # SCENARIO 5: Cancelled Follow-up Rejection
        # ----------------------------------------------------------------------
        print_step("SCENARIO 5: Cancelled Follow-up Rejection")
        fu_canc = FollowUpService.schedule_followup(
            db=db,
            followup_in=FollowUpCreate(
                lead_id=lead.id,
                customer_id=customer.id,
                channel=Channel.WHATSAPP,
                scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
                reason="Check plumbing rough-in dimensions.",
            ),
        )
        await FollowUpService.approve_followup(db=db, followup_id=fu_canc.id, trigger_n8n=False)
        FollowUpService.cancel_followup(
            db=db, followup_id=fu_canc.id, reason="Customer cancelled project."
        )
        print(f"Cancelled Follow-up: {fu_canc.id} (Status: {fu_canc.status})")

        canc_res = N8nFollowUpService.process_event(
            db=db,
            event_data=N8nFollowUpEventRequest(
                delivery_id=fu_canc.delivery_id,
                attempt_id=f"att_canc_{uuid4().hex[:6]}",
                event_type="followup.execute",
                followup_id=fu_canc.id,
            ),
            secret_header=SECRET,
        )
        print(f"Relay Response Status : {canc_res.status} (Expected: CANCELLED)")

        # ----------------------------------------------------------------------
        # SCENARIO 6: Unapproved Follow-up Protection
        # ----------------------------------------------------------------------
        print_step("SCENARIO 6: Unapproved Follow-up Protection")
        fu_unappr = FollowUpService.schedule_followup(
            db=db,
            followup_in=FollowUpCreate(
                lead_id=lead.id,
                customer_id=customer.id,
                channel=Channel.WHATSAPP,
                scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
                reason="Unapproved promotional follow-up.",
            ),
        )
        print(f"Created Follow-up: {fu_unappr.id} (Approval: {fu_unappr.approval_status})")

        unappr_res = N8nFollowUpService.process_event(
            db=db,
            event_data=N8nFollowUpEventRequest(
                delivery_id=fu_unappr.delivery_id,
                attempt_id=f"att_unappr_{uuid4().hex[:6]}",
                event_type="followup.execute",
                followup_id=fu_unappr.id,
            ),
            secret_header=SECRET,
        )
        print(f"Relay Response Status : {unappr_res.status} (Expected: UNAPPROVED)")

        print_header("Demo Completed Successfully!")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
