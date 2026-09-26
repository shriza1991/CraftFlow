"""Customer domain entity representing individual clients or architectural firms."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import CustomerSource

if TYPE_CHECKING:
    from app.db.models.conversation import Conversation
    from app.db.models.follow_up import FollowUp
    from app.db.models.lead import Lead


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Customer entity holding omnichannel contact details and profile history."""

    __tablename__ = "customers"

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    preferred_language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), default=CustomerSource.DIRECT.value, nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    # Relationships
    leads: Mapped[list["Lead"]] = relationship("Lead", back_populates="customer")
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="customer"
    )
    follow_ups: Mapped[list["FollowUp"]] = relationship("FollowUp", back_populates="customer")
