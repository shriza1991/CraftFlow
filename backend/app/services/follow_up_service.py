"""FollowUp domain service managing scheduled client touchpoints."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.core.logging import get_logger
from app.db.models.conversation import Conversation
from app.db.models.customer import Customer
from app.db.models.enums import ActorType, FollowUpStatus
from app.db.models.follow_up import FollowUp
from app.db.models.lead import Lead
from app.integrations.n8n.client import N8nWebhookClient
from app.schemas.follow_up import FollowUpCreate, FollowUpUpdate
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

            meta = dict(followup_in.metadata_) if followup_in.metadata_ else {}
            meta.setdefault("approval_status", "PENDING_APPROVAL")
            meta.setdefault("delivery_status", "PENDING")
            meta.setdefault("delivery_attempts", 0)
            meta.setdefault("max_retries", 3)
            meta.setdefault("delivery_records", [])
            meta.setdefault("processed_event_ids", [])

            follow_up = FollowUp(
                **data,
                metadata_=meta,
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
        """Update follow-up status enforcing state machine rules."""
        follow_up = FollowUpService.get_followup(db, followup_id)
        before_status = follow_up.status
        before_state = {
            "status": before_status,
            "scheduled_at": (
                follow_up.scheduled_at.isoformat() if follow_up.scheduled_at else None
            ),
        }

        update_dict = updates.model_dump(exclude_unset=True)

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

        if "metadata_" in update_dict and update_dict["metadata_"] is not None:
            follow_up.metadata_ = {**follow_up.metadata_, **update_dict.pop("metadata_")}

        for key, value in update_dict.items():
            if key != "status" and value is not None:
                setattr(follow_up, key, value)

        try:
            db.flush()
            db.refresh(follow_up)

            after_state = {
                "status": follow_up.status,
                "scheduled_at": (
                    follow_up.scheduled_at.isoformat() if follow_up.scheduled_at else None
                ),
                "completed_at": (
                    follow_up.completed_at.isoformat() if follow_up.completed_at else None
                ),
            }

            AuditService.record(
                db=db,
                action="FOLLOW_UP_UPDATED",
                entity_type="FollowUp",
                entity_id=follow_up.id,
                actor_id=actor_id,
                actor_type=actor_type,
                description=f"Updated follow-up status from {before_status} to {follow_up.status}.",
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
        """Human approval action: approve follow-up for execution and optionally trigger n8n."""
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

        meta = dict(follow_up.metadata_) if follow_up.metadata_ else {}
        before_state = {
            "status": follow_up.status,
            "approval_status": meta.get("approval_status", "PENDING_APPROVAL"),
        }

        meta["approval_status"] = "APPROVED"
        meta["approved_by"] = actor_id or "system"
        meta["approved_at"] = datetime.now(UTC).isoformat()
        if reviewer_notes:
            meta["reviewer_notes"] = reviewer_notes

        # Transition status to SCHEDULED if it was PENDING
        if follow_up.status == FollowUpStatus.PENDING.value:
            follow_up.status = FollowUpStatus.SCHEDULED.value

        follow_up.metadata_ = meta
        db.flush()
        db.refresh(follow_up)

        AuditService.record(
            db=db,
            action="FOLLOW_UP_APPROVED",
            entity_type="FollowUp",
            entity_id=follow_up.id,
            actor_id=actor_id,
            actor_type=actor_type,
            description=f"Approved follow-up '{follow_up.id}' for lead '{follow_up.lead_id}'.",
            before_state=before_state,
            after_state={
                "status": follow_up.status,
                "approval_status": "APPROVED",
                "approved_by": meta["approved_by"],
            },
        )
        db.commit()

        # Trigger n8n workflow if requested
        if trigger_n8n:
            try:
                client = N8nWebhookClient()
                customer = db.get(Customer, follow_up.customer_id)
                recipient = customer.phone or customer.email if customer else None
                event_payload = {
                    "event_id": f"evt_{uuid4().hex[:16]}",
                    "event_type": "followup.execute",
                    "followup_id": follow_up.id,
                    "customer_id": follow_up.customer_id,
                    "lead_id": follow_up.lead_id,
                    "channel": follow_up.channel,
                    "scheduled_at": follow_up.scheduled_at.isoformat(),
                    "reason": follow_up.reason,
                    "message": follow_up.message_template
                    or f"Follow-up regarding {follow_up.reason}",
                    "recipient": recipient,
                    "approval_status": "APPROVED",
                }
                await client.trigger_workflow(
                    webhook_path="webhook/craftflow-followup",
                    payload=event_payload,
                )
            except Exception as exc:
                logger.warning(f"Non-blocking n8n webhook dispatch warning: {exc}")

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

        meta = dict(follow_up.metadata_) if follow_up.metadata_ else {}
        before_state = {
            "status": follow_up.status,
            "approval_status": meta.get("approval_status", "PENDING_APPROVAL"),
        }

        follow_up.status = FollowUpStatus.CANCELLED.value
        meta["approval_status"] = "CANCELLED"
        meta["delivery_status"] = "CANCELLED"
        meta["cancellation_reason"] = reason
        follow_up.failure_reason = f"Cancelled: {reason}"
        follow_up.metadata_ = meta

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
        """Retrieve structured delivery status, attempts, and delivery audit history."""
        follow_up = FollowUpService.get_followup(db, followup_id)
        meta = dict(follow_up.metadata_) if follow_up.metadata_ else {}

        raw_records = meta.get("delivery_records", [])
        parsed_records: list[DeliveryRecord] = []
        for rec in raw_records:
            try:
                parsed_records.append(
                    DeliveryRecord(
                        event_id=rec.get("event_id", "unknown"),
                        attempt=rec.get("attempt", 1),
                        status=rec.get("status", "PENDING"),
                        timestamp=datetime.fromisoformat(rec["timestamp"])
                        if isinstance(rec.get("timestamp"), str)
                        else rec.get("timestamp", datetime.now(UTC)),
                        provider=rec.get("provider", "mock"),
                        provider_message_id=rec.get("provider_message_id"),
                        recipient=rec.get("recipient"),
                        error=rec.get("error"),
                        retryable=rec.get("retryable", False),
                    )
                )
            except Exception as parse_err:
                logger.debug(f"Could not parse delivery record: {parse_err}")

        return FollowUpDeliveryStatusResponse(
            followup_id=follow_up.id,
            status=follow_up.status,
            approval_status=meta.get("approval_status", "PENDING_APPROVAL"),
            delivery_status=meta.get("delivery_status", "PENDING"),
            delivery_attempts=meta.get("delivery_attempts", 0),
            max_retries=meta.get("max_retries", 3),
            completed_at=follow_up.completed_at,
            failure_reason=follow_up.failure_reason,
            last_event_id=meta.get("last_event_id"),
            delivery_records=parsed_records,
        )
