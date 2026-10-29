"""Customer domain service with international normalization and deterministic deduplication."""

import re

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.db.models.customer import Customer
from app.db.models.enums import ActorType
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.schemas.pagination import PageParams
from app.services.audit_service import AuditService


class CustomerService:
    """Business operations and deterministic contact resolution for customers."""

    @staticmethod
    def normalize_email(email: str | None) -> str | None:
        """Standardize email address to lowercase and trimmed string."""
        if not email:
            return None
        return email.strip().lower()

    @staticmethod
    def normalize_phone(phone: str | None) -> str | None:
        """Standardize phone / WhatsApp number, retaining international plus sign."""
        if not phone:
            return None
        cleaned = re.sub(r"[^\d+]", "", phone.strip())
        return cleaned if cleaned else None

    @classmethod
    def find_existing_customer(
        cls,
        db: Session,
        email: str | None = None,
        phone: str | None = None,
        whatsapp_number: str | None = None,
    ) -> Customer | None:
        """Lookup existing customer deterministically by email, phone, or WhatsApp."""
        norm_email = cls.normalize_email(email)
        norm_phone = cls.normalize_phone(phone)
        norm_wa = cls.normalize_phone(whatsapp_number)

        conditions = []
        if norm_email:
            conditions.append(Customer.email == norm_email)
        if norm_phone:
            conditions.append(Customer.phone == norm_phone)
        if norm_wa:
            conditions.append(Customer.whatsapp_number == norm_wa)

        if not conditions:
            return None

        stmt = select(Customer).where(or_(*conditions))
        return db.scalar(stmt)

    @classmethod
    def create_customer(
        cls,
        db: Session,
        customer_in: CustomerCreate,
        actor_id: str | None = None,
        actor_type: ActorType | str = ActorType.SYSTEM,
    ) -> Customer:
        """Create a new customer after normalizing contact details."""
        norm_email = cls.normalize_email(customer_in.email)
        norm_phone = cls.normalize_phone(customer_in.phone)
        norm_wa = cls.normalize_phone(customer_in.whatsapp_number)

        # Check for duplicate customer
        existing = cls.find_existing_customer(
            db=db, email=norm_email, phone=norm_phone, whatsapp_number=norm_wa
        )
        if existing:
            raise ValidationException(
                message="A customer with matching email, phone, or WhatsApp already exists.",
                details={"existing_customer_id": existing.id},
            )

        try:
            data = customer_in.model_dump(exclude={"metadata_"})
            data["email"] = norm_email
            data["phone"] = norm_phone
            data["whatsapp_number"] = norm_wa

            customer = Customer(
                **data,
                metadata_=customer_in.metadata_,
            )
            db.add(customer)
            db.flush()
            db.refresh(customer)

            AuditService.record(
                db=db,
                action="CUSTOMER_CREATED",
                entity_type="Customer",
                entity_id=customer.id,
                actor_id=actor_id,
                actor_type=actor_type,
                description=f"Created customer '{customer.first_name} {customer.last_name or ''}'.",
                after_state={"email": customer.email, "phone": customer.phone},
            )
            db.commit()
            return customer
        except IntegrityError as err:
            db.rollback()
            raise ValidationException(
                message="A customer with matching email, phone, or WhatsApp already exists.",
                details={"email": norm_email, "phone": norm_phone},
            ) from err
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_customer(db: Session, customer_id: str) -> Customer:
        """Retrieve customer by ID or raise NotFoundException."""
        customer = db.get(Customer, customer_id)
        if not customer:
            raise NotFoundException(
                message=f"Customer with ID '{customer_id}' not found.",
                details={"customer_id": customer_id},
            )
        return customer

    @staticmethod
    def list_customers(
        db: Session,
        page_params: PageParams,
        search: str | None = None,
        active_only: bool = True,
    ) -> tuple[list[Customer], int]:
        """List customers with search and pagination."""
        query = select(Customer)
        count_query = select(func.count(Customer.id))

        if active_only:
            query = query.where(Customer.is_active.is_(True))
            count_query = count_query.where(Customer.is_active.is_(True))

        if search:
            s = f"%{search.strip()}%"
            criteria = or_(
                Customer.first_name.ilike(s),
                Customer.last_name.ilike(s),
                Customer.email.ilike(s),
                Customer.phone.ilike(s),
                Customer.company_name.ilike(s),
            )
            query = query.where(criteria)
            count_query = count_query.where(criteria)

        total = db.scalar(count_query) or 0
        items = list(
            db.scalars(
                query.order_by(Customer.created_at.desc())
                .offset(page_params.offset)
                .limit(page_params.limit)
            ).all()
        )
        return items, total

    @classmethod
    def update_customer(
        cls,
        db: Session,
        customer_id: str,
        updates: CustomerUpdate,
        actor_id: str | None = None,
        actor_type: ActorType | str = ActorType.SYSTEM,
    ) -> Customer:
        """Update customer profile information with normalization."""
        customer = cls.get_customer(db, customer_id)
        before_state = {
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone,
            "whatsapp_number": customer.whatsapp_number,
        }

        update_dict = updates.model_dump(exclude_unset=True)

        if "email" in update_dict:
            update_dict["email"] = cls.normalize_email(update_dict["email"])
        if "phone" in update_dict:
            update_dict["phone"] = cls.normalize_phone(update_dict["phone"])
        if "whatsapp_number" in update_dict:
            update_dict["whatsapp_number"] = cls.normalize_phone(update_dict["whatsapp_number"])

        # Check collision with another customer's contacts
        new_email = update_dict.get("email")
        new_phone = update_dict.get("phone")
        new_wa = update_dict.get("whatsapp_number")
        if new_email or new_phone or new_wa:
            existing = cls.find_existing_customer(
                db=db, email=new_email, phone=new_phone, whatsapp_number=new_wa
            )
            if existing and existing.id != customer.id:
                raise ValidationException(
                    message="A customer with matching email, phone, or WhatsApp already exists.",
                    details={"existing_customer_id": existing.id},
                )

        if "metadata_" in update_dict and update_dict["metadata_"] is not None:
            customer.metadata_ = {**customer.metadata_, **update_dict.pop("metadata_")}

        for key, value in update_dict.items():
            if value is not None:
                setattr(customer, key, value)

        try:
            db.flush()
            db.refresh(customer)

            after_state = {
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "phone": customer.phone,
                "whatsapp_number": customer.whatsapp_number,
            }

            AuditService.record(
                db=db,
                action="CUSTOMER_UPDATED",
                entity_type="Customer",
                entity_id=customer.id,
                actor_id=actor_id,
                actor_type=actor_type,
                description=f"Updated customer profile for '{customer.first_name}'.",
                before_state=before_state,
                after_state=after_state,
            )
            db.commit()
            return customer
        except IntegrityError as err:
            db.rollback()
            raise ValidationException(
                message="A customer with matching email, phone, or WhatsApp already exists.",
                details={"customer_id": customer_id},
            ) from err
        except Exception:
            db.rollback()
            raise
