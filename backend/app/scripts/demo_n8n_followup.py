# ruff: noqa: E402
"""Standalone demo script for CraftFlow n8n integration with approved follow-ups.

Demonstrates:
  1. Approved follow-up moving through n8n automation and mock messaging delivery.
  2. Duplicate event protection (repeated event IDs do not create duplicate sends).
  3. Cancelled follow-up rejection (cancelled touchpoints are not dispatched).
  4. Failure handling, retry progression, and bounded failure exhaustion (max retries).
  5. Unapproved follow-up protection (enforcing backend human approval gate).
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
from app.schemas.follow_up import FollowUpCreate
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
        # SCENARIO 1: Approved Follow-up Moves Through n8n Workflow
        # ----------------------------------------------------------------------
        print_step("SCENARIO 1: Approved Follow-up Moves Through n8n Automation")

        fu_create = FollowUpCreate(
            lead_id=lead.id,
            customer_id=customer.id,
            channel=Channel.WHATSAPP,
            scheduled_at=datetime.now(UTC) + timedelta(days=2),
            reason="Confirm quarry slab inspection and delivery timeline.",
            message_template="Hi Alexander, our artisan team completed the block inspection for your tub.",
        )
        follow_up = FollowUpService.schedule_followup(
            db=db,
            followup_in=fu_create,
            actor_id="sales_agent_rachel",
            actor_type=ActorType.HUMAN,
        )
        print(f"Follow-up Scheduled : {follow_up.id}")
        print(f"Initial Status      : {follow_up.status}")
        print(f"Initial Approval    : {follow_up.metadata_.get('approval_status')}")

        # Human Reviewer Approves Follow-up
        print("\n[Human Action] Reviewing and approving follow-up...")
        approved_fu = await FollowUpService.approve_followup(
            db=db,
            followup_id=follow_up.id,
            actor_id="sales_manager_david",
            trigger_n8n=False,  # We execute via n8n webhook directly below
            reviewer_notes="Client confirmed availability for Thursday morning.",
        )
        print(f"Approval Result     : {approved_fu.metadata_.get('approval_status')}")
        print(f"Approved By         : {approved_fu.metadata_.get('approved_by')}")

        # n8n Relays Execution Event via Authenticated Webhook
        event_1 = f"evt_{uuid4().hex[:12]}"
        req1 = N8nFollowUpEventRequest(
            event_id=event_1,
            event_type="followup.execute",
            followup_id=approved_fu.id,
            attempt=1,
            max_retries=3,
        )
        print(f"\n[n8n Webhook Relay] Dispatching event '{event_1}' to /api/v1/webhooks/n8n...")
        res1 = N8nFollowUpService.process_event(db=db, event_data=req1, secret_header=SECRET)

        print(f"Relay Response Status : {res1.status}")
        print(f"Delivery Status       : {res1.delivery_status}")
        print(
            f"Provider Message ID   : {res1.delivery_record.provider_message_id if res1.delivery_record else 'N/A'}"
        )
        print(f"Message               : {res1.message}")

        # Check visible delivery status
        deliv1 = FollowUpService.get_delivery_status(db, approved_fu.id)
        print(
            f"Visible Status in CRM : {deliv1.delivery_status} (Attempts: {deliv1.delivery_attempts})"
        )

        # ----------------------------------------------------------------------
        # SCENARIO 2: Repeated Event ID Protection (Idempotency)
        # ----------------------------------------------------------------------
        print_step("SCENARIO 2: Repeated Event ID Duplicate Protection (No Duplicate Sends)")
        print(f"[n8n Replay] Re-sending identical event '{event_1}'...")
        res2 = N8nFollowUpService.process_event(db=db, event_data=req1, secret_header=SECRET)
        print(f"Relay Response Status : {res2.status} (Duplicate: {res2.duplicate})")
        print(f"Message               : {res2.message}")

        deliv2 = FollowUpService.get_delivery_status(db, approved_fu.id)
        print(
            f"Total Delivery Attempts Recorded: {len(deliv2.delivery_records)} (Expected: exactly 1)"
        )

        # ----------------------------------------------------------------------
        # SCENARIO 3: Cancelled Follow-up Protection
        # ----------------------------------------------------------------------
        print_step("SCENARIO 3: Cancelled Follow-up Rejection")
        fu_cancel_create = FollowUpCreate(
            lead_id=lead.id,
            customer_id=customer.id,
            channel=Channel.WHATSAPP,
            scheduled_at=datetime.now(UTC) + timedelta(days=5),
            reason="Check plumbing rough-in dimensions.",
        )
        fu_to_cancel = FollowUpService.schedule_followup(
            db=db, followup_in=fu_cancel_create, actor_id="sales_agent"
        )
        await FollowUpService.approve_followup(
            db=db, followup_id=fu_to_cancel.id, actor_id="sales_manager", trigger_n8n=False
        )
        print(f"Follow-up Created & Approved: {fu_to_cancel.id}")

        print("[Human Action] Cancelling follow-up: Customer changed project scope.")
        cancelled_fu = FollowUpService.cancel_followup(
            db=db,
            followup_id=fu_to_cancel.id,
            reason="Customer changed project scope to powder room.",
            actor_id="sales_agent",
        )
        print(f"Follow-up Status: {cancelled_fu.status}")

        print("\n[n8n Webhook Relay] Attempting execution on cancelled follow-up...")
        res3 = N8nFollowUpService.process_event(
            db=db,
            event_data=N8nFollowUpEventRequest(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type="followup.execute",
                followup_id=cancelled_fu.id,
            ),
            secret_header=SECRET,
        )
        print(f"Relay Response Status : {res3.status}")
        print(f"Message               : {res3.message}")
        print(f"Delivery Record Created: {res3.delivery_record is not None} (Expected: False)")

        # ----------------------------------------------------------------------
        # SCENARIO 4: Delivery Failure, Retry Progression, & Bounded Exhaustion
        # ----------------------------------------------------------------------
        print_step("SCENARIO 4: Failure Handling, Retries, & Bounded Exhaustion (Max 3)")
        fu_retry_create = FollowUpCreate(
            lead_id=lead.id,
            customer_id=customer.id,
            channel=Channel.WHATSAPP,
            scheduled_at=datetime.now(UTC) + timedelta(days=7),
            reason="Verify final crating and air-freight booking.",
        )
        fu_retry = FollowUpService.schedule_followup(
            db=db, followup_in=fu_retry_create, actor_id="agent"
        )
        await FollowUpService.approve_followup(
            db=db, followup_id=fu_retry.id, actor_id="manager", trigger_n8n=False
        )

        for attempt in range(1, 4):
            evt_id = f"evt_attempt_{attempt}_{uuid4().hex[:8]}"
            req = N8nFollowUpEventRequest(
                event_id=evt_id,
                event_type="followup.execute",
                followup_id=fu_retry.id,
                attempt=attempt,
                max_retries=3,
                payload={
                    "simulate_failure": True,
                    "simulate_error": "Carrier network gateway timeout (HTTP 504)",
                },
            )
            print(f"\n[n8n Relay Attempt {attempt}/3] Dispatching event '{evt_id}'...")
            res_retry = N8nFollowUpService.process_event(
                db=db, event_data=req, secret_header=SECRET
            )
            print(f"  Attempt Status : {res_retry.status} (Retryable: {res_retry.retryable})")
            print(f"  CRM Status     : {res_retry.delivery_status}")
            print(f"  Message        : {res_retry.message}")

        # Verify bounded exhaustion
        deliv_retry = FollowUpService.get_delivery_status(db, fu_retry.id)
        print("\nFinal State after Max Retries:")
        print(f"  Overall Status : {deliv_retry.status} (Expected: FAILED)")
        print(f"  Failure Reason : {deliv_retry.failure_reason}")
        print(f"  Total Attempts : {len(deliv_retry.delivery_records)} / {deliv_retry.max_retries}")

        # ----------------------------------------------------------------------
        # SCENARIO 5: Unapproved Follow-up Protection
        # ----------------------------------------------------------------------
        print_step("SCENARIO 5: Unapproved Follow-up Protection")
        fu_unapproved_create = FollowUpCreate(
            lead_id=lead.id,
            customer_id=customer.id,
            channel=Channel.WHATSAPP,
            scheduled_at=datetime.now(UTC) + timedelta(days=10),
            reason="Unapproved promotional follow-up.",
        )
        fu_unappr = FollowUpService.schedule_followup(
            db=db, followup_in=fu_unapproved_create, actor_id="agent"
        )
        print(
            f"Created Follow-up: {fu_unappr.id} (Approval: {fu_unappr.metadata_.get('approval_status')})"
        )

        print("[n8n Relay] Attempting execution before human approval...")
        res_unappr = N8nFollowUpService.process_event(
            db=db,
            event_data=N8nFollowUpEventRequest(
                event_id=f"evt_{uuid4().hex[:12]}",
                event_type="followup.execute",
                followup_id=fu_unappr.id,
            ),
            secret_header=SECRET,
        )
        print(f"Relay Response Status : {res_unappr.status}")
        print(f"Delivery Status       : {res_unappr.delivery_status}")
        print(f"Message               : {res_unappr.message}")

        print_header("Demo Completed Successfully!")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
