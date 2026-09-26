"""Unit tests for external integration clients and service wrappers."""

import pytest
from app.core.exceptions import ValidationException
from app.integrations.google.client import GoogleWorkspaceClient
from app.integrations.google.service import GoogleWorkspaceService
from app.integrations.n8n.client import N8nWebhookClient
from app.integrations.whatsapp.client import WhatsAppClient
from app.integrations.whatsapp.service import WhatsAppService


@pytest.mark.asyncio
async def test_whatsapp_service_mock_dispatch():
    """Verify WhatsAppService validates phone and dispatches via client."""
    client = WhatsAppClient(is_mock=True)
    service = WhatsAppService(client=client)

    assert await service.is_ready() is True

    result = await service.send_customer_reply(
        customer_phone="+1 234 567 8900",
        text="Your Carrara marble bathtub inquiry has been received.",
    )
    assert result["messaging_product"] == "whatsapp"
    assert len(result["messages"]) == 1


@pytest.mark.asyncio
async def test_whatsapp_service_validation_failure():
    """Verify WhatsAppService rejects invalid phone numbers or empty messages."""
    service = WhatsAppService()

    with pytest.raises(ValidationException):
        await service.send_customer_reply(customer_phone="", text="Hello")

    with pytest.raises(ValidationException):
        await service.send_customer_reply(customer_phone="+123456", text="   ")


@pytest.mark.asyncio
async def test_google_workspace_service():
    """Verify GoogleWorkspaceService append row mock."""
    client = GoogleWorkspaceClient(is_mock=True)
    service = GoogleWorkspaceService(client=client)

    assert await service.is_ready() is True
    res = await service.log_lead_to_sheet(
        spreadsheet_id="test_sheet_123",
        row_data=["2026-09-26", "VIP Client", "Carrara Marble Tub"],
    )
    assert res["updates"]["updatedRows"] == 1


@pytest.mark.asyncio
async def test_n8n_webhook_client():
    """Verify n8n client triggers workflow in mock mode."""
    client = N8nWebhookClient(is_mock=True)
    res = await client.trigger_workflow(
        webhook_path="/webhook/new-lead",
        payload={"lead_id": "test_123", "source": "whatsapp"},
    )
    assert res["status"] == "dispatched"
    assert res["mock"] is True
