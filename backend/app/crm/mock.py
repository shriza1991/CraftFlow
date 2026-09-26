"""In-memory Mock CRM Provider for offline testing and development."""

from app.core.exceptions import CRMException
from app.crm.base import CRMProvider, Lead, LeadCreate, LeadUpdate


class MockCRMProvider(CRMProvider):
    """In-memory CRM provider simulating external CRM API behavior."""

    def __init__(self) -> None:
        self._leads: dict[str, Lead] = {}

    async def create_lead(self, lead: LeadCreate) -> Lead:
        new_lead = Lead(
            name=lead.name,
            phone=lead.phone,
            email=lead.email,
            source=lead.source,
            budget=lead.budget,
            notes=lead.notes,
            custom_fields=lead.custom_fields,
        )
        self._leads[new_lead.id] = new_lead
        return new_lead

    async def get_lead(self, lead_id: str) -> Lead | None:
        return self._leads.get(lead_id)

    async def update_lead(self, lead_id: str, updates: LeadUpdate) -> Lead:
        existing = self._leads.get(lead_id)
        if not existing:
            raise CRMException(
                message=f"Lead '{lead_id}' not found in CRM.",
                details={"lead_id": lead_id},
            )

        data = existing.model_dump()
        for field, value in updates.model_dump(exclude_unset=True).items():
            if value is not None:
                data[field] = value

        updated = Lead(**data)
        self._leads[lead_id] = updated
        return updated

    async def search_leads(self, query: str) -> list[Lead]:
        q = query.lower()
        return [
            lead
            for lead in self._leads.values()
            if q in lead.name.lower()
            or (lead.email and q in lead.email.lower())
            or (lead.phone and q in lead.phone.lower())
        ]
