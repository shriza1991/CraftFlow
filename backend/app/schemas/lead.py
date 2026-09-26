"""Pydantic schemas for Leads and Lead-Product associations."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.db.models.enums import CustomerSource, LeadPriority, LeadStatus


class LeadProductItem(BaseModel):
    product_id: str
    variant_id: str | None = None
    quantity: int = Field(default=1, ge=1)
    notes: str | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


LeadProductCreate = LeadProductItem


class LeadProductResponse(LeadProductItem):
    id: str
    lead_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LeadBase(BaseModel):
    customer_id: str
    status: LeadStatus = LeadStatus.NEW
    source: CustomerSource = CustomerSource.WEBSITE
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    interest_description: str | None = None
    qualification_score: Decimal | None = Field(default=None, ge=0, le=100)
    priority: LeadPriority = LeadPriority.MEDIUM
    assigned_to: str | None = None
    expected_close_date: datetime | None = None
    last_contacted_at: datetime | None = None
    next_follow_up_at: datetime | None = None
    notes: str | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class LeadCreate(LeadBase):
    products: list[LeadProductItem] = Field(default_factory=list)


class LeadUpdate(BaseModel):
    status: LeadStatus | None = None
    estimated_value: Decimal | None = Field(default=None, ge=0)
    interest_description: str | None = None
    qualification_score: Decimal | None = Field(default=None, ge=0, le=100)
    priority: LeadPriority | None = None
    assigned_to: str | None = None
    expected_close_date: datetime | None = None
    next_follow_up_at: datetime | None = None
    notes: str | None = None
    metadata_: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class LeadResponse(LeadBase):
    id: str
    products: list[LeadProductResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
