"""CRM abstraction layer for decoupling CRM vendors from agent/business logic."""

from app.crm.base import CRMProvider, Lead, LeadCreate, LeadUpdate
from app.crm.mock import MockCRMProvider

__all__ = ["CRMProvider", "Lead", "LeadCreate", "LeadUpdate", "MockCRMProvider"]
