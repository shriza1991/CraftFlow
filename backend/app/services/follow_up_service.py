"""FollowUp domain service managing scheduled client touchpoints."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.db.models.conversation import Conversation
from app.db.models.customer import Customer
from app.db.models.enums import ActorType, FollowUpStatus
from app.db.models.follow_up import FollowUp
from app.db.models.lead import Lead
from app.schemas.follow_up import FollowUpCreate, FollowUpUpdate
from app.schemas.pagination import PageParams
from app.services.audit_service import AuditService


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

            follow_up = FollowUp(
                **data,
                metadata_=followup_in.metadata_,
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
