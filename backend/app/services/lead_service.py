"""Lead domain service managing sales qualification and product association workflows."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundException, ValidationException
from app.db.models.customer import Customer
from app.db.models.enums import LeadStatus
from app.db.models.lead import Lead
from app.db.models.product import LeadProduct, Product
from app.schemas.lead import LeadCreate, LeadUpdate
from app.schemas.pagination import PageParams
from app.services.audit_service import AuditService


class LeadService:
    """Business operations and state machine transitions for sales leads."""

    @staticmethod
    def create_lead(db: Session, lead_in: LeadCreate) -> Lead:
        """Create a sales lead associated with a customer and interested products."""
        # 1. Verify customer exists
        customer = db.get(Customer, lead_in.customer_id)
        if not customer:
            raise NotFoundException(
                message=f"Customer with ID '{lead_in.customer_id}' not found.",
                details={"customer_id": lead_in.customer_id},
            )

        # 2. Verify products exist
        for prod_item in lead_in.products:
            prod = db.get(Product, prod_item.product_id)
            if not prod:
                raise NotFoundException(
                    message=f"Product with ID '{prod_item.product_id}' not found.",
                    details={"product_id": prod_item.product_id},
                )

        lead_data = lead_in.model_dump(exclude={"products", "metadata_"})
        lead = Lead(
            **lead_data,
            metadata_=lead_in.metadata_,
        )
        db.add(lead)
        db.flush()

        # 3. Create lead product associations
        for prod_item in lead_in.products:
            assoc = LeadProduct(
                lead_id=lead.id,
                product_id=prod_item.product_id,
                variant_id=prod_item.variant_id,
                quantity=prod_item.quantity,
                notes=prod_item.notes,
                metadata_=prod_item.metadata_,
            )
            db.add(assoc)

        db.flush()
        db.refresh(lead)

        AuditService.record(
            db=db,
            action="LEAD_CREATED",
            entity_type="Lead",
            entity_id=lead.id,
            description=f"Created lead for customer '{customer.first_name}' with status '{lead.status}'.",
            after_state={"customer_id": lead.customer_id, "status": lead.status},
        )
        db.commit()
        return lead

    @staticmethod
    def get_lead(db: Session, lead_id: str) -> Lead:
        """Retrieve lead by ID with product associations or raise NotFoundException."""
        stmt = (
            select(Lead)
            .where(Lead.id == lead_id)
            .options(selectinload(Lead.products), selectinload(Lead.customer))
        )
        lead = db.scalar(stmt)
        if not lead:
            raise NotFoundException(
                message=f"Lead with ID '{lead_id}' not found.",
                details={"lead_id": lead_id},
            )
        return lead

    @staticmethod
    def list_leads(
        db: Session,
        page_params: PageParams,
        status: LeadStatus | None = None,
        customer_id: str | None = None,
    ) -> tuple[list[Lead], int]:
        """List leads with filtering and pagination."""
        query = select(Lead).options(selectinload(Lead.products))
        count_query = select(func.count(Lead.id))

        if status:
            query = query.where(Lead.status == status.value)
            count_query = count_query.where(Lead.status == status.value)

        if customer_id:
            query = query.where(Lead.customer_id == customer_id)
            count_query = count_query.where(Lead.customer_id == customer_id)

        total = db.scalar(count_query) or 0
        items = list(
            db.scalars(
                query.order_by(Lead.created_at.desc())
                .offset(page_params.offset)
                .limit(page_params.limit)
            ).all()
        )
        return items, total

    @staticmethod
    def update_lead(db: Session, lead_id: str, updates: LeadUpdate) -> Lead:
        """Update lead fields with state-machine transition validation."""
        lead = LeadService.get_lead(db, lead_id)
        before_status = lead.status

        update_dict = updates.model_dump(exclude_unset=True)

        # Enforce deterministic state machine rules
        if "status" in update_dict and update_dict["status"] is not None:
            new_status = update_dict["status"].value if hasattr(update_dict["status"], "value") else str(update_dict["status"])
            if before_status == LeadStatus.LOST.value and new_status == LeadStatus.WON.value:
                raise ValidationException(
                    message="A lead marked as LOST cannot directly transition to WON without requalification.",
                    details={"current_status": before_status, "requested_status": new_status},
                )
            lead.status = new_status

        if "metadata_" in update_dict and update_dict["metadata_"] is not None:
            lead.metadata_ = {**lead.metadata_, **update_dict.pop("metadata_")}

        for key, value in update_dict.items():
            if key != "status" and value is not None:
                setattr(lead, key, value)

        db.flush()
        db.refresh(lead)

        AuditService.record(
            db=db,
            action="LEAD_UPDATED",
            entity_type="Lead",
            entity_id=lead.id,
            description=f"Updated lead status from {before_status} to {lead.status}.",
            before_state={"status": before_status},
            after_state={"status": lead.status},
        )
        db.commit()
        return lead
