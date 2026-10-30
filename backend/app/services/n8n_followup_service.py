"""Service managing n8n follow-up webhook events, idempotency, bounded retries, and delivery tracking."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.core.logging import get_logger
from app.core.security import WebhookAuthenticationError, verify_webhook_secret
from app.db.models.conversation import Conversation
from app.db.models.customer import Customer
from app.db.models.enums import (
    ActorType,
    Channel,
    ConversationStatus,
    FollowUpStatus,
    MessageDirection,
    MessageStatus,
    MessageType,
    SenderType,
)
from app.db.models.follow_up import FollowUp
from app.db.models.follow_up_delivery_attempt import FollowUpDeliveryAttempt
from app.db.models.message import Message
from app.schemas.follow_up import FollowUpCreate
from app.schemas.n8n_webhook import (
    DeliveryRecord,
    N8nFollowUpEventRequest,
    N8nFollowUpEventResponse,
)
from app.services.audit_service import AuditService
from app.services.follow_up_service import FollowUpService

logger = get_logger(__name__)


class N8nFollowUpService:
    """Processes incoming n8n webhook events for follow-up orchestration and delivery."""

    @staticmethod
    def verify_auth(secret_header: str | None) -> None:
        """Verify webhook secret or raise WebhookAuthenticationError."""
        if not verify_webhook_secret(secret_header):
            raise WebhookAuthenticationError(
                message="Invalid or missing n8n webhook secret header 'X-Webhook-Secret'.",
                details={"header": "X-Webhook-Secret"},
            )

    @classmethod
    def process_event(
        cls,
        db: Session,
        event_data: N8nFollowUpEventRequest,
        secret_header: str | None,
    ) -> N8nFollowUpEventResponse:
        """Process inbound n8n webhook event with idempotency, approval verification, and bounded retries."""
        # 1. Authenticate webhook
        cls.verify_auth(secret_header)

        # 2. Dispatch based on event_type
        if event_data.event_type == "followup.execute":
            return cls._execute_followup(db, event_data)
        elif event_data.event_type == "followup.schedule":
            return cls._schedule_followup(db, event_data)
        elif event_data.event_type == "followup.cancel":
            return cls._cancel_followup(db, event_data)
        else:
            raise ValidationException(
                message=f"Unsupported event_type '{event_data.event_type}'.",
                details={"event_type": event_data.event_type},
            )

    @classmethod
    def _execute_followup(
        cls, db: Session, event_data: N8nFollowUpEventRequest
    ) -> N8nFollowUpEventResponse:
        """Execute an approved follow-up with atomic concurrency locking, scheduling checks, and bounded retries."""
        now = datetime.now(UTC)

        # 1. Atomic row-level lock on the target follow-up
        follow_up = db.scalar(
            select(FollowUp).where(FollowUp.id == event_data.followup_id).with_for_update()
        )
        if not follow_up:
            raise NotFoundException(
                message=f"FollowUp '{event_data.followup_id}' not found.",
                details={"followup_id": event_data.followup_id},
            )

        delivery_id = (
            follow_up.delivery_id or f"del_{follow_up.id[:8]}_v{follow_up.schedule_version}"
        )
        attempt_id = event_data.attempt_id or event_data.event_id or f"att_{uuid4().hex[:12]}"

        # 2. Idempotency Check: Replaying the exact same attempt identifier
        existing_attempt = db.scalar(
            select(FollowUpDeliveryAttempt).where(FollowUpDeliveryAttempt.attempt_id == attempt_id)
        )
        if existing_attempt:
            # If we previously completed this attempt, return its recorded outcome without repeating the send
            if existing_attempt.response_payload:
                cached_data = dict(existing_attempt.response_payload)
                cached_data["duplicate"] = True
                cached_data["status"] = "DUPLICATE_REPLAY"
                cached_data["message"] = (
                    f"Duplicate attempt replay '{attempt_id}': returning previously recorded outcome."
                )
                if cached_data.get("timestamp") and isinstance(cached_data["timestamp"], str):
                    cached_data["timestamp"] = datetime.fromisoformat(cached_data["timestamp"])
                if cached_data.get("next_eligible_at") and isinstance(
                    cached_data["next_eligible_at"], str
                ):
                    cached_data["next_eligible_at"] = datetime.fromisoformat(
                        cached_data["next_eligible_at"]
                    )
                if cached_data.get("delivery_record") and isinstance(
                    cached_data["delivery_record"].get("timestamp"), str
                ):
                    cached_data["delivery_record"]["timestamp"] = datetime.fromisoformat(
                        cached_data["delivery_record"]["timestamp"]
                    )
                return N8nFollowUpEventResponse(**cached_data)

            # If attempt is still in CLAIMED state and not expired
            if existing_attempt.status == "CLAIMED" and existing_attempt.claim_expires_at > now:
                return N8nFollowUpEventResponse(
                    delivery_id=existing_attempt.delivery_id,
                    attempt_id=existing_attempt.attempt_id,
                    event_id=existing_attempt.attempt_id,
                    followup_id=follow_up.id,
                    schedule_version=existing_attempt.schedule_version,
                    status="CLAIM_ACTIVE",
                    delivery_status=follow_up.delivery_status,
                    attempt=existing_attempt.attempt,
                    max_retries=follow_up.max_retries,
                    retryable=False,
                    next_eligible_at=existing_attempt.claim_expires_at,
                    message="Attempt currently claimed by an active delivery worker. Please wait.",
                    duplicate=True,
                    delivery_record=None,
                    timestamp=now,
                )

        # 3. Check Cancellation Invariant
        if (
            follow_up.status == FollowUpStatus.CANCELLED.value
            or follow_up.approval_status == "CANCELLED"
        ):
            return N8nFollowUpEventResponse(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                event_id=attempt_id,
                followup_id=follow_up.id,
                schedule_version=follow_up.schedule_version,
                status="CANCELLED",
                delivery_status="CANCELLED",
                attempt=follow_up.current_attempt,
                max_retries=follow_up.max_retries,
                retryable=False,
                message="Follow-up has been cancelled. No message dispatched.",
                duplicate=False,
                delivery_record=None,
                timestamp=now,
            )

        # 4. Check Approval Invariant: Human approval required before delivery
        if follow_up.approval_status != "APPROVED":
            return N8nFollowUpEventResponse(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                event_id=attempt_id,
                followup_id=follow_up.id,
                schedule_version=follow_up.schedule_version,
                status="UNAPPROVED",
                delivery_status=follow_up.delivery_status,
                attempt=follow_up.current_attempt,
                max_retries=follow_up.max_retries,
                retryable=False,
                message="Follow-up has not been approved for execution. Human approval required.",
                duplicate=False,
                delivery_record=None,
                timestamp=now,
            )

        # 5. Check Rescheduled / Stale Execution Invariant
        # If the incoming event references an older schedule version or mismatched delivery_id, reject
        is_stale_version = (
            event_data.schedule_version is not None
            and event_data.schedule_version < follow_up.schedule_version
        )
        is_mismatched_delivery = (
            event_data.delivery_id is not None
            and event_data.delivery_id != follow_up.delivery_id
            and event_data.delivery_id != event_data.event_id  # disregard if only default fallback
        )
        if is_stale_version or (is_mismatched_delivery and follow_up.delivery_id):
            return N8nFollowUpEventResponse(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                event_id=attempt_id,
                followup_id=follow_up.id,
                schedule_version=follow_up.schedule_version,
                status="STALE_SCHEDULE",
                delivery_status=follow_up.delivery_status,
                attempt=follow_up.current_attempt,
                max_retries=follow_up.max_retries,
                retryable=False,
                next_eligible_at=follow_up.scheduled_at,
                message=(
                    f"Stale schedule execution rejected. Follow-up was rescheduled to version "
                    f"{follow_up.schedule_version} with delivery_id '{follow_up.delivery_id}' "
                    f"due at {follow_up.scheduled_at.isoformat()}."
                ),
                duplicate=False,
                delivery_record=None,
                timestamp=now,
            )

        # 6. Check Due Time: Reject execution before follow-up is due without consuming an attempt
        if now < follow_up.scheduled_at:
            return N8nFollowUpEventResponse(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                event_id=attempt_id,
                followup_id=follow_up.id,
                schedule_version=follow_up.schedule_version,
                status="NOT_DUE",
                delivery_status=follow_up.delivery_status,
                attempt=follow_up.current_attempt,
                max_retries=follow_up.max_retries,
                retryable=False,
                next_eligible_at=follow_up.scheduled_at,
                message=(
                    f"Follow-up is not due yet. Scheduled for {follow_up.scheduled_at.isoformat()}. "
                    f"Next eligible execution at {follow_up.scheduled_at.isoformat()}."
                ),
                duplicate=False,
                delivery_record=None,
                timestamp=now,
            )

        # 7. Check Completion Invariant: Prevent duplicate sends if already delivered
        if (
            follow_up.status == FollowUpStatus.COMPLETED.value
            or follow_up.delivery_status == "DELIVERED"
        ):
            # Fetch last successful delivery attempt record
            last_att = db.scalar(
                select(FollowUpDeliveryAttempt)
                .where(
                    FollowUpDeliveryAttempt.follow_up_id == follow_up.id,
                    FollowUpDeliveryAttempt.status == "DELIVERED",
                )
                .order_by(FollowUpDeliveryAttempt.attempt.desc())
            )
            last_record = cls._to_delivery_record(last_att) if last_att else None

            return N8nFollowUpEventResponse(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                event_id=attempt_id,
                followup_id=follow_up.id,
                schedule_version=follow_up.schedule_version,
                status="ALREADY_COMPLETED",
                delivery_status="DELIVERED",
                attempt=follow_up.current_attempt,
                max_retries=follow_up.max_retries,
                retryable=False,
                message="Follow-up has already been successfully completed. Duplicate send prevented.",
                duplicate=True,
                delivery_record=last_record,
                timestamp=now,
            )

        # 8. Attempt Limits & Retry Eligibility
        # Calculate next attempt number strictly in the backend
        highest_att_num = (
            db.scalar(
                select(func.max(FollowUpDeliveryAttempt.attempt)).where(
                    FollowUpDeliveryAttempt.follow_up_id == follow_up.id,
                    FollowUpDeliveryAttempt.delivery_id == delivery_id,
                )
            )
            or 0
        )
        next_attempt = highest_att_num + 1

        # Check if terminal failure reached
        if next_attempt > follow_up.max_retries:
            follow_up.status = FollowUpStatus.FAILED.value
            follow_up.delivery_status = "FAILED"
            db.commit()

            return N8nFollowUpEventResponse(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                event_id=attempt_id,
                followup_id=follow_up.id,
                schedule_version=follow_up.schedule_version,
                status="FAILED",
                delivery_status="FAILED",
                attempt=follow_up.current_attempt,
                max_retries=follow_up.max_retries,
                retryable=False,
                message=f"Delivery failed and max retries ({follow_up.max_retries}) exhausted.",
                duplicate=False,
                delivery_record=None,
                timestamp=now,
            )

        # 9. Atomic Execution Claim: Create attempt record with CLAIMED status and timeout
        claim_timeout = now + timedelta(minutes=5)
        customer = db.get(Customer, follow_up.customer_id)
        recipient = (customer.phone or customer.email or "customer") if customer else "customer"
        content = (
            follow_up.message_template
            or f"Hello {customer.first_name if customer else 'Customer'}, following up regarding {follow_up.reason}."
        )

        attempt_record_db = FollowUpDeliveryAttempt(
            id=str(uuid4()),
            follow_up_id=follow_up.id,
            delivery_id=delivery_id,
            schedule_version=follow_up.schedule_version,
            attempt=next_attempt,
            attempt_id=attempt_id,
            status="CLAIMED",
            claimed_at=now,
            claim_expires_at=claim_timeout,
            provider="mock",
            recipient=recipient,
            retryable=False,
        )
        db.add(attempt_record_db)
        follow_up.current_attempt = next_attempt
        db.flush()

        # 10. Execute Delivery via Mock Provider
        simulate_failure = bool(event_data.payload.get("simulate_failure", False))
        simulate_error = str(
            event_data.payload.get("simulate_error", "Simulated messaging network timeout")
        )

        if not simulate_failure:
            # === SUCCESS PATH ===
            provider_msg_id = f"mock_wamid_{uuid4().hex[:12]}"
            completed_now = datetime.now(UTC)

            follow_up.status = FollowUpStatus.COMPLETED.value
            follow_up.completed_at = completed_now
            follow_up.delivery_status = "DELIVERED"
            follow_up.failure_reason = None

            # Persist outbound message in conversation
            conv = cls._get_or_create_conversation(db, follow_up)
            outbound_msg = Message(
                conversation_id=conv.id,
                external_message_id=provider_msg_id,
                direction=MessageDirection.OUTBOUND.value,
                sender_type=SenderType.SYSTEM.value,
                message_type=MessageType.TEXT.value,
                content=content,
                status=MessageStatus.SENT.value,
                sent_at=completed_now,
                metadata_={
                    "follow_up_id": follow_up.id,
                    "delivery_id": delivery_id,
                    "attempt_id": attempt_id,
                    "attempt": next_attempt,
                    "provider": "mock",
                },
            )
            db.add(outbound_msg)

            # Finalize attempt record
            attempt_record_db.status = "DELIVERED"
            attempt_record_db.completed_at = completed_now
            attempt_record_db.provider_message_id = provider_msg_id
            attempt_record_db.error = None
            attempt_record_db.retryable = False

            record = cls._to_delivery_record(attempt_record_db)
            response = N8nFollowUpEventResponse(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                event_id=attempt_id,
                followup_id=follow_up.id,
                schedule_version=follow_up.schedule_version,
                status="DELIVERED",
                delivery_status="DELIVERED",
                attempt=next_attempt,
                max_retries=follow_up.max_retries,
                retryable=False,
                message="Follow-up message delivered successfully.",
                duplicate=False,
                delivery_record=record,
                timestamp=completed_now,
            )

            # Store serialized response payload for duplicate replay caching
            attempt_record_db.response_payload = response.model_dump(mode="json")
            db.flush()

            AuditService.record(
                db=db,
                action="FOLLOW_UP_DELIVERED",
                entity_type="FollowUp",
                entity_id=follow_up.id,
                actor_id="n8n_integration",
                actor_type=ActorType.WEBHOOK,
                description=f"Delivered follow-up '{follow_up.id}' on attempt {next_attempt}.",
                after_state={
                    "status": follow_up.status,
                    "delivery_status": "DELIVERED",
                    "provider_message_id": provider_msg_id,
                },
            )
            db.commit()
            return response
        else:
            # === FAILURE / RETRY PATH ===
            failed_now = datetime.now(UTC)
            is_retryable = next_attempt < follow_up.max_retries

            if is_retryable:
                follow_up.status = FollowUpStatus.PROCESSING.value
                follow_up.delivery_status = "RETRYING"
                follow_up.failure_reason = (
                    f"Attempt {next_attempt} failed: {simulate_error}. Retry pending."
                )
                action_name = "FOLLOW_UP_DELIVERY_RETRYING"
                response_status = "RETRYING"
                resp_message = (
                    f"Delivery failed on attempt {next_attempt}; eligible for retry "
                    f"({next_attempt}/{follow_up.max_retries})."
                )
            else:
                follow_up.status = FollowUpStatus.FAILED.value
                follow_up.delivery_status = "FAILED"
                follow_up.failure_reason = (
                    f"Max retries ({follow_up.max_retries}) exhausted. Last error: {simulate_error}"
                )
                action_name = "FOLLOW_UP_DELIVERY_FAILED"
                response_status = "FAILED"
                resp_message = (
                    f"Delivery failed and max retries ({follow_up.max_retries}) exhausted."
                )

            attempt_record_db.status = "FAILED"
            attempt_record_db.completed_at = failed_now
            attempt_record_db.error = simulate_error
            attempt_record_db.retryable = is_retryable

            record = cls._to_delivery_record(attempt_record_db)
            response = N8nFollowUpEventResponse(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                event_id=attempt_id,
                followup_id=follow_up.id,
                schedule_version=follow_up.schedule_version,
                status=response_status,
                delivery_status=follow_up.delivery_status,
                attempt=next_attempt,
                max_retries=follow_up.max_retries,
                retryable=is_retryable,
                next_eligible_at=failed_now if is_retryable else None,
                message=resp_message,
                duplicate=False,
                delivery_record=record,
                timestamp=failed_now,
            )

            # Store serialized response payload for duplicate replay caching
            attempt_record_db.response_payload = response.model_dump(mode="json")
            db.flush()

            AuditService.record(
                db=db,
                action=action_name,
                entity_type="FollowUp",
                entity_id=follow_up.id,
                actor_id="n8n_integration",
                actor_type=ActorType.WEBHOOK,
                description=f"Follow-up delivery failed on attempt {next_attempt}: {simulate_error}",
                after_state={
                    "status": follow_up.status,
                    "delivery_status": follow_up.delivery_status,
                    "error": simulate_error,
                    "retryable": is_retryable,
                },
            )
            db.commit()
            return response

    @classmethod
    def _schedule_followup(
        cls, db: Session, event_data: N8nFollowUpEventRequest
    ) -> N8nFollowUpEventResponse:
        """Schedule a follow-up via webhook with deduplication to prevent duplicate creation."""
        now = datetime.now(UTC)
        payload = event_data.payload
        lead_id = payload.get("lead_id")
        customer_id = payload.get("customer_id")
        scheduled_at_str = payload.get("scheduled_at")
        reason = payload.get("reason", "Scheduled follow-up via n8n")

        if not lead_id or not customer_id or not scheduled_at_str:
            raise ValidationException(
                message="lead_id, customer_id, and scheduled_at are required to schedule a follow-up.",
                details={"payload": payload},
            )

        # Enforce explicit timezone requirement
        scheduled_at = datetime.fromisoformat(scheduled_at_str)
        if scheduled_at.tzinfo is None or scheduled_at.tzinfo.utcoffset(scheduled_at) is None:
            raise ValidationException(
                message="scheduled_at must include an explicit timezone offset.",
                details={"scheduled_at": scheduled_at_str},
            )
        scheduled_at = scheduled_at.astimezone(UTC)

        # Deduplication check: check if a follow-up exists for this lead at the exact same scheduled timestamp
        existing = db.scalar(
            select(FollowUp).where(
                FollowUp.lead_id == lead_id,
                FollowUp.customer_id == customer_id,
                FollowUp.scheduled_at == scheduled_at,
            )
        )
        if existing:
            return N8nFollowUpEventResponse(
                delivery_id=existing.delivery_id or f"del_{existing.id[:8]}",
                attempt_id=event_data.attempt_id
                or event_data.event_id
                or f"att_{uuid4().hex[:12]}",
                event_id=event_data.event_id or f"evt_{uuid4().hex[:12]}",
                followup_id=existing.id,
                schedule_version=existing.schedule_version,
                status="DUPLICATE_IGNORED",
                delivery_status=existing.delivery_status,
                attempt=1,
                max_retries=existing.max_retries,
                retryable=False,
                message="Follow-up already scheduled for this lead and timestamp. Duplicate creation prevented.",
                duplicate=True,
                delivery_record=None,
                timestamp=now,
            )

        followup_in = FollowUpCreate(
            lead_id=lead_id,
            customer_id=customer_id,
            channel=Channel(payload.get("channel", "WHATSAPP")),
            scheduled_at=scheduled_at,
            reason=reason,
            message_template=payload.get("message_template"),
        )
        fu = FollowUpService.schedule_followup(
            db=db,
            followup_in=followup_in,
            actor_id="n8n_integration",
            actor_type=ActorType.WEBHOOK,
        )

        return N8nFollowUpEventResponse(
            delivery_id=fu.delivery_id or f"del_{fu.id[:8]}",
            attempt_id=event_data.attempt_id or event_data.event_id or f"att_{uuid4().hex[:12]}",
            event_id=event_data.event_id or f"evt_{uuid4().hex[:12]}",
            followup_id=fu.id,
            schedule_version=fu.schedule_version,
            status="DELIVERED",  # action succeeded
            delivery_status=fu.delivery_status,
            attempt=1,
            max_retries=fu.max_retries,
            retryable=False,
            message=f"Follow-up scheduled successfully with ID {fu.id}.",
            duplicate=False,
            delivery_record=None,
            timestamp=now,
        )

    @classmethod
    def _cancel_followup(
        cls, db: Session, event_data: N8nFollowUpEventRequest
    ) -> N8nFollowUpEventResponse:
        """Cancel a follow-up via webhook."""
        now = datetime.now(UTC)
        reason = str(event_data.payload.get("reason", "Cancelled via n8n automation"))
        fu = FollowUpService.cancel_followup(
            db=db,
            followup_id=event_data.followup_id,
            reason=reason,
            actor_id="n8n_integration",
            actor_type=ActorType.WEBHOOK,
        )
        return N8nFollowUpEventResponse(
            delivery_id=fu.delivery_id or f"del_{fu.id[:8]}",
            attempt_id=event_data.attempt_id or event_data.event_id or f"att_{uuid4().hex[:12]}",
            event_id=event_data.event_id or f"evt_{uuid4().hex[:12]}",
            followup_id=fu.id,
            schedule_version=fu.schedule_version,
            status="CANCELLED",
            delivery_status="CANCELLED",
            attempt=fu.current_attempt,
            max_retries=fu.max_retries,
            retryable=False,
            message="Follow-up cancelled successfully.",
            duplicate=False,
            delivery_record=None,
            timestamp=now,
        )

    @staticmethod
    def _get_or_create_conversation(db: Session, follow_up: FollowUp) -> Conversation:
        """Find the follow-up's conversation or find/create an open conversation for the customer."""
        if follow_up.conversation_id:
            conv = db.get(Conversation, follow_up.conversation_id)
            if conv:
                return conv

        existing_conv = db.scalar(
            select(Conversation)
            .where(
                Conversation.customer_id == follow_up.customer_id,
                Conversation.status == ConversationStatus.OPEN.value,
            )
            .order_by(Conversation.created_at.desc())
        )
        if existing_conv:
            follow_up.conversation_id = existing_conv.id
            return existing_conv

        new_conv = Conversation(
            customer_id=follow_up.customer_id,
            channel=follow_up.channel,
            status=ConversationStatus.OPEN.value,
            started_at=datetime.now(UTC),
        )
        db.add(new_conv)
        db.flush()
        follow_up.conversation_id = new_conv.id
        return new_conv

    @staticmethod
    def _to_delivery_record(att: FollowUpDeliveryAttempt) -> DeliveryRecord:
        """Helper to convert a FollowUpDeliveryAttempt DB model into a DeliveryRecord schema."""
        return DeliveryRecord(
            attempt_id=att.attempt_id,
            delivery_id=att.delivery_id,
            attempt=att.attempt,
            status=att.status,
            timestamp=att.completed_at or att.claimed_at,
            provider=att.provider,
            provider_message_id=att.provider_message_id,
            recipient=att.recipient,
            error=att.error,
            retryable=att.retryable,
        )
