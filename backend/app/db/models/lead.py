"""Lead domain entity representing sales qualification opportunities."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import CustomerSource, LeadPriority, LeadStatus

if TYPE_CHECKING:
    from app.db.models.agent_run import AgentRun
    from app.db.models.customer import Customer
    from app.db.models.follow_up import FollowUp
    from app.db.models.product import LeadProduct


class Lead(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Sales lead opportunity qualified through AI, website, or WhatsApp channels."""

    __tablename__ = "leads"

    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(
        String(50), default=LeadStatus.NEW.value, nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(
        String(50), default=CustomerSource.WEBSITE.value, nullable=False
    )

    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    interest_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    priority: Mapped[str] = mapped_column(
        String(50), default=LeadPriority.MEDIUM.value, nullable=False
    )

    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_close_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="leads")
    products: Mapped[list["LeadProduct"]] = relationship(
        "LeadProduct", back_populates="lead", cascade="all, delete-orphan"
    )
    follow_ups: Mapped[list["FollowUp"]] = relationship(
        "FollowUp", back_populates="lead", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship("AgentRun", back_populates="lead")
