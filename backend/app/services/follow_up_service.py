"""FollowUp domain service managing scheduled client touchpoints, approvals, and automation dispatch."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.logging import get_logger
from app.db.models.conversation import Conversation
from app.db.models.customer import Customer
from app.db.models.enums import ActorType, FollowUpStatus
from app.db.models.follow_up import FollowUp
from app.db.models.lead import Lead
from app.integrations.n8n.client import N8nWebhookClient
from app.schemas.follow_up import (
    PROTECTED_METADATA_KEYS,
    FollowUpCreate,
    FollowUpUpdate,
)
from app.schemas.n8n_webhook import DeliveryRecord, FollowUpDeliveryStatusResponse
from app.schemas.pagination import PageParams
from app.services.audit_service import AuditService

logger = get_logger(__name__)


class FollowUpService:
    """Operations and validation state transitions for scheduled business follow-ups."""

    @staticmethod
    def schedule_followup(
        db: Session,
        followup_in: FollowUpCreate,
        actor_id: str | None = None,
        actor_type: ActorType | str = ActorType.SYSTEM,
    ) -> FollowUp:
        """Schedule a follow-up touchpoint linked to a lead and customer."""
        lead = db.get(Lead, followup_in.lead_id)
        if not lead:
            raise NotFoundException(
                message=f"Lead with ID '{followup_in.lead_id}' not found.",
                details={"lead_id": followup_in.lead_id},
            )

        customer = db.get(Customer, followup_in.customer_id)
        if not customer:
            raise NotFoundException(
                message=f"Customer with ID '{followup_in.customer_id}' not found.",
                details={"customer_id": followup_in.customer_id},
            )

        # Invariant: Follow-up customer must match the lead's owner customer
        if lead.customer_id != followup_in.customer_id:
            raise ValidationException(
                message=f"Customer '{followup_in.customer_id}' does not own Lead '{followup_in.lead_id}'.",
                details={
                    "customer_id": followup_in.customer_id,
                    "lead_id": followup_in.lead_id,
                    "lead_customer_id": lead.customer_id,
                },
            )

        # Invariant: If conversation_id is provided, it must belong to the customer
        if followup_in.conversation_id:
            conv = db.get(Conversation, followup_in.conversation_id)
            if not conv:
                raise NotFoundException(
                    message=f"Conversation with ID '{followup_in.conversation_id}' not found.",
                    details={"conversation_id": followup_in.conversation_id},
                )
            if conv.customer_id != followup_in.customer_id:
                raise ValidationException(
                    message=f"Conversation '{conv.id}' belongs to Customer '{conv.customer_id}', not '{followup_in.customer_id}'.",
                    details={
                        "conversation_id": conv.id,
                        "conversation_customer_id": conv.customer_id,
                        "customer_id": followup_in.customer_id,
                    },
                )

        # Duplicate handling: reject duplicate pending follow-up for same lead at same scheduled time
        existing_fu = db.scalar(
            select(FollowUp).where(
                FollowUp.lead_id == followup_in.lead_id,
                FollowUp.customer_id == followup_in.customer_id,
                FollowUp.scheduled_at == followup_in.scheduled_at,
                FollowUp.status == FollowUpStatus.PENDING.value,
            )
        )
        if existing_fu:
            raise ValidationException(
                message="A pending follow-up is already scheduled for this lead at the specified time.",
                details={"existing_followup_id": existing_fu.id},
            )

        try:
            data = followup_in.model_dump(exclude={"metadata_"})
            data["channel"] = (
                followup_in.channel.value
                if hasattr(followup_in.channel, "value")
                else str(followup_in.channel)
            )
            data["status"] = (
                followup_in.status.value
                if hasattr(followup_in.status, "value")
                else str(followup_in.status)
            )

            # Protect backend-owned state: strip protected keys from client metadata
            raw_meta = dict(followup_in.metadata_) if followup_in.metadata_ else {}
            clean_meta = {k: v for k, v in raw_meta.items() if k not in PROTECTED_METADATA_KEYS}

            # Generate stable initial delivery_id and scheduling version
            delivery_id = f"del_{uuid4().hex[:16]}"

            follow_up = FollowUp(
                **data,
                approval_status="PENDING_APPROVAL",
                delivery_status="PENDING",
                delivery_id=delivery_id,
                schedule_version=1,
                current_attempt=0,
                max_retries=3,
                n8n_dispatch_status="PENDING",
                n8n_dispatch_error=None,
                n8n_dispatched_at=None,
                metadata_=clean_meta,
            )
            db.add(follow_up)

            # Update lead next_follow_up_at
            lead.next_follow_up_at = follow_up.scheduled_at

            db.flush()
            db.refresh(follow_up)

            AuditService.record(
                db=db,
                action="FOLLOW_UP_SCHEDULED",
                entity_type="FollowUp",
                entity_id=follow_up.id,
                actor_id=actor_id,
                actor_type=actor_type,
                description=f"Scheduled follow-up for lead '{lead.id}' on {follow_up.scheduled_at.isoformat()}.",
                after_state={
                    "scheduled_at": follow_up.scheduled_at.isoformat(),
                    "status": follow_up.status,
                    "approval_status": follow_up.approval_status,
                    "delivery_id": follow_up.delivery_id,
                    "schedule_version": follow_up.schedule_version,
                    "lead_id": follow_up.lead_id,
                    "customer_id": follow_up.customer_id,
                },
            )
            db.commit()
            return follow_up
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_followup(db: Session, followup_id: str) -> FollowUp:
        """Retrieve follow-up by ID or raise NotFoundException."""
        follow_up = db.get(FollowUp, followup_id)
        if not follow_up:
            raise NotFoundException(
                message=f"FollowUp with ID '{followup_id}' not found.",
                details={"followup_id": followup_id},
            )
        return follow_up

    @staticmethod
    def list_followups(
        db: Session,
        page_params: PageParams,
        status: FollowUpStatus | None = None,
        lead_id: str | None = None,
    ) -> tuple[list[FollowUp], int]:
        """List follow-ups with pagination and filtering."""
        query = select(FollowUp)
        count_query = select(func.count(FollowUp.id))

        if status:
            query = query.where(FollowUp.status == status.value)
            count_query = count_query.where(FollowUp.status == status.value)

        if lead_id:
            query = query.where(FollowUp.lead_id == lead_id)
            count_query = count_query.where(FollowUp.lead_id == lead_id)

        total = db.scalar(count_query) or 0
        items = list(
            db.scalars(
                query.order_by(FollowUp.scheduled_at.asc())
                .offset(page_params.offset)
                .limit(page_params.limit)
            ).all()
        )
        return items, total

    @staticmethod
    def update_followup(
        db: Session,
        followup_id: str,
        updates: FollowUpUpdate,
        actor_id: str | None = None,
        actor_type: ActorType | str = ActorType.SYSTEM,
    ) -> FollowUp:
        """Update follow-up attributes or reschedule enforcing scheduling invariants and state protection."""
        follow_up = FollowUpService.get_followup(db, followup_id)
        before_status = follow_up.status
        before_scheduled_at = follow_up.scheduled_at
        before_schedule_version = follow_up.schedule_version
        before_state = {
            "status": before_status,
            "scheduled_at": (
                follow_up.scheduled_at.isoformat() if follow_up.scheduled_at else None
            ),
            "schedule_version": follow_up.schedule_version,
            "delivery_id": follow_up.delivery_id,
        }

        update_dict = updates.model_dump(exclude_unset=True)

        # 1. Status transition business rules
        if "status" in update_dict and update_dict["status"] is not None:
            new_status = (
                update_dict["status"].value
                if hasattr(update_dict["status"], "value")
                else str(update_dict["status"])
            )
            # Enforce business rule: completed follow-up cannot return to PENDING
            if (
                before_status == FollowUpStatus.COMPLETED.value
                and new_status == FollowUpStatus.PENDING.value
            ):
                raise ValidationException(
                    message="A COMPLETED follow-up cannot be returned to PENDING status.",
                    details={"current_status": before_status, "requested_status": new_status},
                )
            follow_up.status = new_status
            if new_status == FollowUpStatus.COMPLETED.value and not follow_up.completed_at:
                follow_up.completed_at = datetime.now(UTC)
                follow_up.delivery_status = "DELIVERED"

        # 2. Rescheduling invariant: invalidates older queued executions
        if "scheduled_at" in update_dict and update_dict["scheduled_at"] is not None:
            new_scheduled_at = update_dict["scheduled_at"]
            if follow_up.status in {
                FollowUpStatus.COMPLETED.value,
                FollowUpStatus.CANCELLED.value,
            }:
                raise ValidationException(
                    message=f"Cannot reschedule a follow-up in status '{follow_up.status}'.",
                    details={"status": follow_up.status},
                )

            if new_scheduled_at != before_scheduled_at:
                follow_up.scheduled_at = new_scheduled_at
                follow_up.schedule_version += 1
                # Generate new delivery_id for the new schedule version
                follow_up.delivery_id = f"del_{uuid4().hex[:16]}"
                follow_up.delivery_status = "PENDING"
                follow_up.current_attempt = 0
                follow_up.n8n_dispatch_status = "PENDING"
                follow_up.n8n_dispatch_error = None
                follow_up.n8n_dispatched_at = None

                lead = db.get(Lead, follow_up.lead_id)
                if lead:
                    lead.next_follow_up_at = new_scheduled_at

        # 3. Protect backend-owned state from client metadata tampering
        if "metadata_" in update_dict and update_dict["metadata_"] is not None:
            client_meta = update_dict.pop("metadata_")
            sanitized_meta = {
                k: v for k, v in client_meta.items() if k not in PROTECTED_METADATA_KEYS
            }
            follow_up.metadata_ = {**follow_up.metadata_, **sanitized_meta}

        for key, value in update_dict.items():
            if key not in {"status", "scheduled_at"} and value is not None:
                setattr(follow_up, key, value)

        try:
            db.flush()
            db.refresh(follow_up)

            after_state = {
                "status": follow_up.status,
                "scheduled_at": (
                    follow_up.scheduled_at.isoformat() if follow_up.scheduled_at else None
                ),
                "schedule_version": follow_up.schedule_version,
                "delivery_id": follow_up.delivery_id,
                "completed_at": (
                    follow_up.completed_at.isoformat() if follow_up.completed_at else None
                ),
            }

            desc = f"Updated follow-up status from {before_status} to {follow_up.status}."
            if follow_up.schedule_version > before_schedule_version:
                desc = (
                    f"Rescheduled follow-up to {follow_up.scheduled_at.isoformat()} "
                    f"(version {follow_up.schedule_version}, new delivery_id {follow_up.delivery_id})."
                )

            AuditService.record(
                db=db,
                action="FOLLOW_UP_UPDATED",
                entity_type="FollowUp",
                entity_id=follow_up.id,
                actor_id=actor_id,
                actor_type=actor_type,
                description=desc,
                before_state=before_state,
                after_state=after_state,
            )
            db.commit()
            return follow_up
        except Exception:
            db.rollback()
            raise

    @staticmethod
    async def approve_followup(
        db: Session,
        followup_id: str,
        actor_id: str | None = None,
        actor_type: ActorType | str = ActorType.HUMAN,
        trigger_n8n: bool = True,
        reviewer_notes: str | None = None,
    ) -> FollowUp:
        """Human approval action: authorizes scheduled execution and optionally triggers n8n dispatch.

        Approval authorizes a follow-up; it does NOT mark it delivered.
        """
        follow_up = FollowUpService.get_followup(db, followup_id)

        # Enforce business invariant: cannot approve completed or cancelled follow-ups
        if follow_up.status == FollowUpStatus.CANCELLED.value:
            raise ValidationException(
                message="Cannot approve a cancelled follow-up.",
                details={"followup_id": followup_id, "status": follow_up.status},
            )
        if follow_up.status == FollowUpStatus.COMPLETED.value:
            raise ValidationException(
                message="Cannot approve an already completed follow-up.",
                details={"followup_id": followup_id, "status": follow_up.status},
            )

        before_state = {
            "status": follow_up.status,
            "approval_status": follow_up.approval_status,
        }

        follow_up.approval_status = "APPROVED"

        # Record reviewer notes in metadata if provided
        if reviewer_notes:
            meta = dict(follow_up.metadata_)
            meta["reviewer_notes"] = reviewer_notes
            follow_up.metadata_ = meta

        # Transition status to SCHEDULED if it was PENDING
        if follow_up.status == FollowUpStatus.PENDING.value:
            follow_up.status = FollowUpStatus.SCHEDULED.value

        db.flush()
        db.refresh(follow_up)

        AuditService.record(
            db=db,
            action="FOLLOW_UP_APPROVED",
            entity_type="FollowUp",
            entity_id=follow_up.id,
            actor_id=actor_id,
            actor_type=actor_type,
            description=f"Approved follow-up '{follow_up.id}' for lead '{follow_up.lead_id}'. Authorized for execution.",
            before_state=before_state,
            after_state={
                "status": follow_up.status,
                "approval_status": "APPROVED",
                "scheduled_at": follow_up.scheduled_at.isoformat(),
            },
        )
        db.commit()

        # Trigger n8n workflow dispatch if requested
        if trigger_n8n:
            await FollowUpService.dispatch_followup_to_n8n(
                db=db,
                followup_id=follow_up.id,
                actor_id=actor_id,
                actor_type=actor_type,
            )

        return follow_up

    @staticmethod
    async def dispatch_followup_to_n8n(
        db: Session,
        followup_id: str,
        actor_id: str | None = None,
        actor_type: ActorType | str = ActorType.HUMAN,
    ) -> FollowUp:
        """Dispatch an approved follow-up to n8n.

        Persists dispatch status and errors so an approved follow-up cannot silently lose its automation trigger.
        Safe to retry without creating duplicate logical deliveries.
        """
        follow_up = FollowUpService.get_followup(db, followup_id)

        if follow_up.approval_status != "APPROVED":
            raise ValidationException(
                message="Follow-up must be approved by a human before dispatching to n8n.",
                details={"followup_id": followup_id, "approval_status": follow_up.approval_status},
            )

        if follow_up.status in {
            FollowUpStatus.COMPLETED.value,
            FollowUpStatus.CANCELLED.value,
        }:
            raise ValidationException(
                message=f"Cannot dispatch follow-up in terminal status '{follow_up.status}'.",
                details={"followup_id": followup_id, "status": follow_up.status},
            )

        customer = db.get(Customer, follow_up.customer_id)
        recipient = (customer.phone or customer.email) if customer else None

        # Build execution payload with stable delivery_id, schedule version, and explicit UTC scheduled_at
        event_payload = {
            "delivery_id": follow_up.delivery_id,
            "attempt_id": f"att_1_{follow_up.delivery_id}",
            "event_id": f"att_1_{follow_up.delivery_id}",
            "event_type": "followup.execute",
            "followup_id": follow_up.id,
            "schedule_version": follow_up.schedule_version,
            "scheduled_at": follow_up.scheduled_at.isoformat(),
            "customer_id": follow_up.customer_id,
            "lead_id": follow_up.lead_id,
            "channel": follow_up.channel,
            "reason": follow_up.reason,
            "message": follow_up.message_template or f"Follow-up regarding {follow_up.reason}",
            "recipient": recipient,
            "approval_status": "APPROVED",
            "max_retries": follow_up.max_retries,
        }

        settings = get_settings()
        client = N8nWebhookClient()

        try:
            await client.trigger_workflow(
                webhook_path=settings.N8N_FOLLOWUP_WEBHOOK_PATH,
                payload=event_payload,
            )
            follow_up.n8n_dispatch_status = "DISPATCHED"
            follow_up.n8n_dispatched_at = datetime.now(UTC)
            follow_up.n8n_dispatch_error = None

            AuditService.record(
                db=db,
                action="FOLLOW_UP_N8N_DISPATCHED",
                entity_type="FollowUp",
                entity_id=follow_up.id,
                actor_id=actor_id,
                actor_type=actor_type,
                description=f"Dispatched follow-up '{follow_up.id}' to n8n ({follow_up.n8n_dispatch_status}).",
                after_state={
                    "n8n_dispatch_status": "DISPATCHED",
                    "delivery_id": follow_up.delivery_id,
                    "schedule_version": follow_up.schedule_version,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to dispatch follow-up {follow_up.id} to n8n: {exc}")
            follow_up.n8n_dispatch_status = "FAILED"
            follow_up.n8n_dispatch_error = str(exc)

            AuditService.record(
                db=db,
                action="FOLLOW_UP_N8N_DISPATCH_FAILED",
                entity_type="FollowUp",
                entity_id=follow_up.id,
                actor_id=actor_id,
                actor_type=actor_type,
                description=f"Failed to dispatch follow-up '{follow_up.id}' to n8n: {exc}",
                after_state={
                    "n8n_dispatch_status": "FAILED",
                    "n8n_dispatch_error": str(exc),
                    "delivery_id": follow_up.delivery_id,
                },
            )

        db.flush()
        db.commit()
        return follow_up

    @staticmethod
    def cancel_followup(
        db: Session,
        followup_id: str,
        reason: str,
        actor_id: str | None = None,
        actor_type: ActorType | str = ActorType.HUMAN,
    ) -> FollowUp:
        """Cancel a pending or scheduled follow-up."""
        follow_up = FollowUpService.get_followup(db, followup_id)

        if follow_up.status == FollowUpStatus.COMPLETED.value:
            raise ValidationException(
                message="Cannot cancel an already completed follow-up.",
                details={"followup_id": followup_id, "status": follow_up.status},
            )

        before_state = {
            "status": follow_up.status,
            "approval_status": follow_up.approval_status,
        }

        follow_up.status = FollowUpStatus.CANCELLED.value
        follow_up.approval_status = "CANCELLED"
        follow_up.delivery_status = "CANCELLED"
        follow_up.failure_reason = f"Cancelled: {reason}"

        db.flush()
        db.refresh(follow_up)

        AuditService.record(
            db=db,
            action="FOLLOW_UP_CANCELLED",
            entity_type="FollowUp",
            entity_id=follow_up.id,
            actor_id=actor_id,
            actor_type=actor_type,
            description=f"Cancelled follow-up '{follow_up.id}': {reason}",
            before_state=before_state,
            after_state={
                "status": follow_up.status,
                "approval_status": "CANCELLED",
                "cancellation_reason": reason,
            },
        )
        db.commit()
        return follow_up

    @staticmethod
    def get_delivery_status(db: Session, followup_id: str) -> FollowUpDeliveryStatusResponse:
        """Retrieve structured delivery status, attempts, and delivery audit history from database records."""
        follow_up = FollowUpService.get_followup(db, followup_id)

        # Query database-backed delivery attempts
        attempts = list(follow_up.delivery_attempts)
        parsed_records: list[DeliveryRecord] = []
        for att in attempts:
            parsed_records.append(
                DeliveryRecord(
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
            )

        last_event_id = parsed_records[-1].attempt_id if parsed_records else None

        return FollowUpDeliveryStatusResponse(
            followup_id=follow_up.id,
            status=follow_up.status,
            approval_status=follow_up.approval_status,
            delivery_status=follow_up.delivery_status,
            delivery_id=follow_up.delivery_id,
            schedule_version=follow_up.schedule_version,
            current_attempt=follow_up.current_attempt,
            delivery_attempts=follow_up.current_attempt,
            max_retries=follow_up.max_retries,
            scheduled_at=follow_up.scheduled_at,
            completed_at=follow_up.completed_at,
            failure_reason=follow_up.failure_reason,
            n8n_dispatch_status=follow_up.n8n_dispatch_status,
            n8n_dispatch_error=follow_up.n8n_dispatch_error,
            n8n_dispatched_at=follow_up.n8n_dispatched_at,
            last_event_id=last_event_id,
            delivery_records=parsed_records,
        )
