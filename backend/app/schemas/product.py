"""Pydantic schemas for Products and Product Variants."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.db.models.enums import ProductAvailability


class ProductVariantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    sku_suffix: str = Field(..., min_length=1, max_length=50)
    length: Decimal | None = Field(default=None, gt=0)
    width: Decimal | None = Field(default=None, gt=0)
    height: Decimal | None = Field(default=None, gt=0)
    material: str | None = Field(default=None, max_length=100)
    finish: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=100)
    price_adjustment: Decimal = Field(default=Decimal("0.00"))
    currency: str = Field(default="USD", min_length=3, max_length=3)
    availability_status: ProductAvailability = ProductAvailability.MADE_TO_ORDER
    is_custom: bool = False
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantResponse(ProductVariantBase):
    id: str
    product_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ProductBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = None
    material: str = Field(..., min_length=1, max_length=100)
    style: str | None = Field(default=None, max_length=100)
    category: str = Field(default="Bathtub", max_length=100)
    length: Decimal | None = Field(default=None, gt=0)
    width: Decimal | None = Field(default=None, gt=0)
    height: Decimal | None = Field(default=None, gt=0)
    weight: Decimal | None = Field(default=None, gt=0)
    base_price: Decimal = Field(..., ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lead_time_days: int = Field(default=60, ge=0)
    availability_status: ProductAvailability = ProductAvailability.MADE_TO_ORDER
    is_customizable: bool = True
    is_active: bool = True
    warranty_description: str | None = None
    installation_notes: str | None = None
    shipping_notes: str | None = None
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class ProductCreate(ProductBase):
    variants: list[ProductVariantCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    short_description: str | None = None
    description: str | None = None
    material: str | None = None
    style: str | None = None
    base_price: Decimal | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    availability_status: ProductAvailability | None = None
    is_active: bool | None = None
    metadata_: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class ProductResponse(ProductBase):
    id: str
    variants: list[ProductVariantResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
