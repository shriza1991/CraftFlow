"""FollowUp domain service managing scheduled client touchpoints."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.db.models.customer import Customer
from app.db.models.enums import FollowUpStatus
from app.db.models.follow_up import FollowUp
from app.db.models.lead import Lead
from app.schemas.follow_up import FollowUpCreate, FollowUpUpdate
from app.schemas.pagination import PageParams
from app.services.audit_service import AuditService


class FollowUpService:
    """Operations and validation state transitions for scheduled business follow-ups."""

    @staticmethod
    def schedule_followup(db: Session, followup_in: FollowUpCreate) -> FollowUp:
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
            description=f"Scheduled follow-up for lead '{lead.id}' on {follow_up.scheduled_at.isoformat()}.",
            after_state={"scheduled_at": follow_up.scheduled_at.isoformat(), "status": follow_up.status},
        )
        db.commit()
        return follow_up

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
    def update_followup(db: Session, followup_id: str, updates: FollowUpUpdate) -> FollowUp:
        """Update follow-up status enforcing state machine rules."""
        follow_up = FollowUpService.get_followup(db, followup_id)
        before_status = follow_up.status

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

        db.flush()
        db.refresh(follow_up)

        AuditService.record(
            db=db,
            action="FOLLOW_UP_UPDATED",
            entity_type="FollowUp",
            entity_id=follow_up.id,
            description=f"Updated follow-up status from {before_status} to {follow_up.status}.",
            before_state={"status": before_status},
            after_state={"status": follow_up.status},
        )
        db.commit()
        return follow_up
