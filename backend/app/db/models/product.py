"""Product, ProductVariant, and LeadProduct association models."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import ProductAvailability

if TYPE_CHECKING:
    from app.db.models.lead import Lead


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Catalog item representing a product or service."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("base_price >= 0", name="ck_products_base_price_non_negative"),
        CheckConstraint("lead_time_days >= 0", name="ck_products_lead_time_non_negative"),
    )

    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Architectural specs
    material: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(
        String(100), default="General", nullable=False, index=True
    )

    length: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    width: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    height: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Commercial terms
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    availability_status: Mapped[str] = mapped_column(
        String(50), default=ProductAvailability.MADE_TO_ORDER.value, nullable=False
    )

    is_customizable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    warranty_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    installation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    seo_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    # Relationships
    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan"
    )
    lead_associations: Mapped[list["LeadProduct"]] = relationship(
        "LeadProduct", back_populates="product"
    )


class ProductVariant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Specific dimension, finish, or stone cut variant of a product."""

    __tablename__ = "product_variants"

    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku_suffix: Mapped[str] = mapped_column(String(50), nullable=False)

    length: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    width: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    height: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    material: Mapped[str | None] = mapped_column(String(100), nullable=True)
    finish: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)

    price_adjustment: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    availability_status: Mapped[str] = mapped_column(
        String(50), default=ProductAvailability.MADE_TO_ORDER.value, nullable=False
    )

    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="variants")


class LeadProduct(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Many-to-many relationship association between Leads and interested Products."""

    __tablename__ = "lead_products"

    lead_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    variant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )

    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="products")
    product: Mapped["Product"] = relationship("Product", back_populates="lead_associations")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
