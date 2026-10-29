"""Service managing n8n follow-up webhook events, idempotency, bounded retries, and delivery tracking."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
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
        """Execute an approved follow-up with idempotency and retry bounding."""
        follow_up = db.get(FollowUp, event_data.followup_id)
        if not follow_up:
            raise NotFoundException(
                message=f"FollowUp '{event_data.followup_id}' not found.",
                details={"followup_id": event_data.followup_id},
            )

        meta = dict(follow_up.metadata_) if follow_up.metadata_ else {}
        processed_events = meta.setdefault("processed_event_ids", [])
        delivery_records_raw = meta.setdefault("delivery_records", [])

        # Invariant 1: Duplicate Event Protection (Idempotency)
        if event_data.event_id in processed_events:
            last_record = cls._parse_last_record(delivery_records_raw)
            return N8nFollowUpEventResponse(
                event_id=event_data.event_id,
                followup_id=follow_up.id,
                status="DUPLICATE_IGNORED",
                delivery_status=meta.get("delivery_status", "DELIVERED"),
                attempt=event_data.attempt,
                max_retries=event_data.max_retries,
                retryable=False,
                message="Duplicate event ignored; follow-up already processed for this event_id.",
                duplicate=True,
                delivery_record=last_record,
                timestamp=datetime.now(UTC),
            )

        # Invariant 2: Cancellation Rule
        if (
            follow_up.status == FollowUpStatus.CANCELLED.value
            or meta.get("approval_status") == "CANCELLED"
        ):
            return N8nFollowUpEventResponse(
                event_id=event_data.event_id,
                followup_id=follow_up.id,
                status="CANCELLED",
                delivery_status="CANCELLED",
                attempt=event_data.attempt,
                max_retries=event_data.max_retries,
                retryable=False,
                message="Follow-up has been cancelled. No message dispatched.",
                duplicate=False,
                delivery_record=None,
                timestamp=datetime.now(UTC),
            )

        # Invariant 3: Backend Approval State Check
        if meta.get("approval_status") != "APPROVED":
            return N8nFollowUpEventResponse(
                event_id=event_data.event_id,
                followup_id=follow_up.id,
                status="UNAPPROVED",
                delivery_status="PENDING_APPROVAL",
                attempt=event_data.attempt,
                max_retries=event_data.max_retries,
                retryable=False,
                message="Follow-up has not been approved for execution. Human approval required.",
                duplicate=False,
                delivery_record=None,
                timestamp=datetime.now(UTC),
            )

        # Invariant 4: Already Completed (Prevent Duplicate Sends)
        if follow_up.status == FollowUpStatus.COMPLETED.value:
            last_record = cls._parse_last_record(delivery_records_raw)
            processed_events.append(event_data.event_id)
            meta["processed_event_ids"] = processed_events
            follow_up.metadata_ = meta
            db.commit()

            return N8nFollowUpEventResponse(
                event_id=event_data.event_id,
                followup_id=follow_up.id,
                status="ALREADY_COMPLETED",
                delivery_status="DELIVERED",
                attempt=event_data.attempt,
                max_retries=event_data.max_retries,
                retryable=False,
                message="Follow-up has already been successfully completed. Duplicate send prevented.",
                duplicate=True,
                delivery_record=last_record,
                timestamp=datetime.now(UTC),
            )

        # Determine Recipient & Message Content
        customer = db.get(Customer, follow_up.customer_id)
        recipient = (customer.phone or customer.email or "customer") if customer else "customer"
        content = (
            follow_up.message_template
            or f"Hello {customer.first_name if customer else 'Customer'}, following up regarding {follow_up.reason}."
        )

        # Check simulation flags for controllable testing
        simulate_failure = bool(event_data.payload.get("simulate_failure", False))
        simulate_error = str(
            event_data.payload.get("simulate_error", "Simulated messaging network timeout")
        )

        current_attempt = meta.get("delivery_attempts", 0) + 1
        meta["delivery_attempts"] = current_attempt
        meta["last_event_id"] = event_data.event_id
        max_retries = event_data.max_retries or meta.get("max_retries", 3)
        meta["max_retries"] = max_retries

        if not simulate_failure:
            # === SUCCESS PATH ===
            provider_msg_id = f"mock_wamid_{uuid4().hex[:12]}"
            follow_up.status = FollowUpStatus.COMPLETED.value
            follow_up.completed_at = datetime.now(UTC)
            meta["delivery_status"] = "DELIVERED"
            follow_up.failure_reason = None

            # Record Outbound Conversation Message
            conv = cls._get_or_create_conversation(db, follow_up)
            outbound_msg = Message(
                conversation_id=conv.id,
                external_message_id=provider_msg_id,
                direction=MessageDirection.OUTBOUND.value,
                sender_type=SenderType.SYSTEM.value,
                message_type=MessageType.TEXT.value,
                content=content,
                status=MessageStatus.SENT.value,
                sent_at=datetime.now(UTC),
                metadata_={
                    "follow_up_id": follow_up.id,
                    "event_id": event_data.event_id,
                    "attempt": current_attempt,
                    "provider": "mock",
                },
            )
            db.add(outbound_msg)

            attempt_record = {
                "event_id": event_data.event_id,
                "attempt": current_attempt,
                "status": "DELIVERED",
                "timestamp": datetime.now(UTC).isoformat(),
                "provider": "mock",
                "provider_message_id": provider_msg_id,
                "recipient": recipient,
                "error": None,
                "retryable": False,
            }
            delivery_records_raw.append(attempt_record)
            processed_events.append(event_data.event_id)

            meta["delivery_records"] = delivery_records_raw
            meta["processed_event_ids"] = processed_events
            follow_up.metadata_ = meta
            db.flush()

            AuditService.record(
                db=db,
                action="FOLLOW_UP_DELIVERED",
                entity_type="FollowUp",
                entity_id=follow_up.id,
                actor_id="n8n_integration",
                actor_type=ActorType.WEBHOOK,
                description=f"Delivered follow-up '{follow_up.id}' on attempt {current_attempt}.",
                after_state={
                    "status": follow_up.status,
                    "delivery_status": "DELIVERED",
                    "provider_message_id": provider_msg_id,
                },
            )
            db.commit()

            return N8nFollowUpEventResponse(
                event_id=event_data.event_id,
                followup_id=follow_up.id,
                status="DELIVERED",
                delivery_status="DELIVERED",
                attempt=current_attempt,
                max_retries=max_retries,
                retryable=False,
                message="Follow-up message delivered successfully.",
                duplicate=False,
                delivery_record=DeliveryRecord(**attempt_record),
                timestamp=datetime.now(UTC),
            )
        else:
            # === FAILURE / RETRY PATH ===
            retryable = current_attempt < max_retries

            if retryable:
                follow_up.status = FollowUpStatus.PROCESSING.value
                meta["delivery_status"] = "RETRYING"
                follow_up.failure_reason = (
                    f"Attempt {current_attempt} failed: {simulate_error}. Retry pending."
                )
                action_name = "FOLLOW_UP_DELIVERY_RETRYING"
                response_status = "RETRYING"
                resp_message = f"Delivery failed on attempt {current_attempt}; eligible for retry ({current_attempt}/{max_retries})."
            else:
                follow_up.status = FollowUpStatus.FAILED.value
                meta["delivery_status"] = "FAILED"
                follow_up.failure_reason = (
                    f"Max retries ({max_retries}) exhausted. Last error: {simulate_error}"
                )
                action_name = "FOLLOW_UP_DELIVERY_FAILED"
                response_status = "FAILED"
                resp_message = f"Delivery failed and max retries ({max_retries}) exhausted."

            attempt_record = {
                "event_id": event_data.event_id,
                "attempt": current_attempt,
                "status": "FAILED",
                "timestamp": datetime.now(UTC).isoformat(),
                "provider": "mock",
                "provider_message_id": None,
                "recipient": recipient,
                "error": simulate_error,
                "retryable": retryable,
            }
            delivery_records_raw.append(attempt_record)
            processed_events.append(event_data.event_id)

            meta["delivery_records"] = delivery_records_raw
            meta["processed_event_ids"] = processed_events
            follow_up.metadata_ = meta
            db.flush()

            AuditService.record(
                db=db,
                action=action_name,
                entity_type="FollowUp",
                entity_id=follow_up.id,
                actor_id="n8n_integration",
                actor_type=ActorType.WEBHOOK,
                description=f"Follow-up delivery failed on attempt {current_attempt}: {simulate_error}",
                after_state={
                    "status": follow_up.status,
                    "delivery_status": meta["delivery_status"],
                    "error": simulate_error,
                    "retryable": retryable,
                },
            )
            db.commit()

            return N8nFollowUpEventResponse(
                event_id=event_data.event_id,
                followup_id=follow_up.id,
                status=response_status,
                delivery_status=meta["delivery_status"],
                attempt=current_attempt,
                max_retries=max_retries,
                retryable=retryable,
                message=resp_message,
                duplicate=False,
                delivery_record=DeliveryRecord(**attempt_record),
                timestamp=datetime.now(UTC),
            )

    @classmethod
    def _schedule_followup(
        cls, db: Session, event_data: N8nFollowUpEventRequest
    ) -> N8nFollowUpEventResponse:
        """Schedule a follow-up via webhook with deduplication to prevent duplicate creation."""
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

        scheduled_at = datetime.fromisoformat(scheduled_at_str)

        # Deduplication check: check if a follow-up with this scheduling event_id or lead/time exists
        existing = db.scalar(
            select(FollowUp).where(
                FollowUp.lead_id == lead_id,
                FollowUp.customer_id == customer_id,
                FollowUp.scheduled_at == scheduled_at,
            )
        )
        if existing:
            return N8nFollowUpEventResponse(
                event_id=event_data.event_id,
                followup_id=existing.id,
                status="DUPLICATE_IGNORED",
                delivery_status=existing.metadata_.get("delivery_status", "PENDING"),
                attempt=1,
                max_retries=3,
                retryable=False,
                message="Follow-up already scheduled for this lead and timestamp. Duplicate creation prevented.",
                duplicate=True,
                delivery_record=None,
                timestamp=datetime.now(UTC),
            )

        followup_in = FollowUpCreate(
            lead_id=lead_id,
            customer_id=customer_id,
            channel=Channel(payload.get("channel", "WHATSAPP")),
            scheduled_at=scheduled_at,
            reason=reason,
            message_template=payload.get("message_template"),
            metadata_={"scheduling_event_id": event_data.event_id},
        )
        fu = FollowUpService.schedule_followup(
            db=db,
            followup_in=followup_in,
            actor_id="n8n_integration",
            actor_type=ActorType.WEBHOOK,
        )

        return N8nFollowUpEventResponse(
            event_id=event_data.event_id,
            followup_id=fu.id,
            status="DELIVERED",  # action completed successfully
            delivery_status="PENDING",
            attempt=1,
            max_retries=3,
            retryable=False,
            message=f"Follow-up scheduled successfully with ID {fu.id}.",
            duplicate=False,
            delivery_record=None,
            timestamp=datetime.now(UTC),
        )

    @classmethod
    def _cancel_followup(
        cls, db: Session, event_data: N8nFollowUpEventRequest
    ) -> N8nFollowUpEventResponse:
        """Cancel a follow-up via webhook."""
        reason = str(event_data.payload.get("reason", "Cancelled via n8n automation"))
        fu = FollowUpService.cancel_followup(
            db=db,
            followup_id=event_data.followup_id,
            reason=reason,
            actor_id="n8n_integration",
            actor_type=ActorType.WEBHOOK,
        )
        return N8nFollowUpEventResponse(
            event_id=event_data.event_id,
            followup_id=fu.id,
            status="CANCELLED",
            delivery_status="CANCELLED",
            attempt=event_data.attempt,
            max_retries=event_data.max_retries,
            retryable=False,
            message="Follow-up cancelled successfully.",
            duplicate=False,
            delivery_record=None,
            timestamp=datetime.now(UTC),
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
    def _parse_last_record(records: list[dict]) -> DeliveryRecord | None:
        """Helper to parse the latest delivery record if available."""
        if not records:
            return None
        last = records[-1]
        try:
            return DeliveryRecord(
                event_id=last.get("event_id", "unknown"),
                attempt=last.get("attempt", 1),
                status=last.get("status", "PENDING"),
                timestamp=datetime.fromisoformat(last["timestamp"])
                if isinstance(last.get("timestamp"), str)
                else last.get("timestamp", datetime.now(UTC)),
                provider=last.get("provider", "mock"),
                provider_message_id=last.get("provider_message_id"),
                recipient=last.get("recipient"),
                error=last.get("error"),
                retryable=last.get("retryable", False),
            )
        except Exception:
            return None
