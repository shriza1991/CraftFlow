"""WhatsApp Domain Service wrapping client calls with business validation."""

from typing import Any

from app.core.exceptions import ValidationException
from app.integrations.base import ExternalService
from app.integrations.whatsapp.client import WhatsAppClient


class WhatsAppService(ExternalService):
    """Business service for handling outgoing customer communications via WhatsApp."""

    def __init__(self, client: WhatsAppClient | None = None):
        self.client = client or WhatsAppClient(is_mock=True)

    async def is_ready(self) -> bool:
        return await self.client.ping()

    async def send_customer_reply(self, customer_phone: str, text: str) -> dict[str, Any]:
        """Validate input phone number and dispatch customer message."""
        clean_phone = customer_phone.strip().replace(" ", "").replace("-", "")
        if not clean_phone:
            raise ValidationException(
                message="Valid customer phone number is required.",
                details={"phone": customer_phone},
            )

        if not text.strip():
            raise ValidationException(
                message="Cannot send an empty message.",
                details={"text": text},
            )

        return await self.client.send_text_message(to_phone=clean_phone, message=text)
