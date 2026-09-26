"""Unit tests for CRM provider abstraction and mock implementation."""

import pytest
from app.crm.base import LeadCreate, LeadUpdate
from app.crm.mock import MockCRMProvider


@pytest.mark.asyncio
async def test_mock_crm_provider():
    """Verify lead creation, retrieval, updating, and search in MockCRMProvider."""
    crm = MockCRMProvider()

    # 1. Create Lead
    created = await crm.create_lead(
        LeadCreate(
            name="Alexander Wright",
            email="alexander@luxuryarchitects.com",
            phone="+1-555-0192",
            budget=25000.0,
            notes="Interested in monolithic Carrara marble tub for penthouse project.",
        )
    )
    assert created.id is not None
    assert created.name == "Alexander Wright"
    assert created.status == "new"

    # 2. Get Lead
    fetched = await crm.get_lead(created.id)
    assert fetched is not None
    assert fetched.email == "alexander@luxuryarchitects.com"

    # 3. Update Lead
    updated = await crm.update_lead(
        created.id,
        LeadUpdate(status="qualified", notes="Sample sent to architectural firm."),
    )
    assert updated.status == "qualified"
    assert updated.notes == "Sample sent to architectural firm."

    # 4. Search Leads
    results = await crm.search_leads("Alexander")
    assert len(results) == 1
    assert results[0].id == created.id
