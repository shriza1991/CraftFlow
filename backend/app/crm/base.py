"""CRM abstract provider interface and data contracts."""

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class Lead(BaseModel):
    """Normalized CRM lead representation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    phone: str | None = None
    email: str | None = None
    status: str = "new"
    source: str = "direct"
    budget: float | None = None
    notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LeadCreate(BaseModel):
    """Payload to create a new lead in CRM."""

    name: str
    phone: str | None = None
    email: str | None = None
    source: str = "website"
    budget: float | None = None
    notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class LeadUpdate(BaseModel):
    """Payload to update an existing lead."""

    name: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str | None = None
    budget: float | None = None
    notes: str | None = None
    custom_fields: dict[str, Any] | None = None


class CRMProvider(ABC):
    """Abstract interface defining required CRM capabilities."""

    @abstractmethod
    async def create_lead(self, lead: LeadCreate) -> Lead:
        """Create a new lead in CRM."""
        pass

    @abstractmethod
    async def get_lead(self, lead_id: str) -> Lead | None:
        """Retrieve lead by ID."""
        pass

    @abstractmethod
    async def update_lead(self, lead_id: str, updates: LeadUpdate) -> Lead:
        """Update an existing lead by ID."""
        pass

    @abstractmethod
    async def search_leads(self, query: str) -> list[Lead]:
        """Search leads by contact info or name."""
        pass
