"""WhatsApp Cloud API low-level HTTP client."""

from typing import Any

import httpx

from app.core.exceptions import ExternalServiceException
from app.integrations.base import ExternalClient


class WhatsAppClient(ExternalClient):
    """Client for Meta WhatsApp Business Cloud API."""

    def __init__(
        self,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        api_version: str = "v20.0",
        is_mock: bool = True,
    ):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.is_mock = is_mock
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    async def ping(self) -> bool:
        if self.is_mock:
            return True
        if not self.access_token or not self.phone_number_id:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.base_url}/{self.phone_number_id}",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )
                return res.status_code == 200
        except Exception:
            return False

    async def send_text_message(self, to_phone: str, message: str) -> dict[str, Any]:
        """Send a standard text message."""
        if self.is_mock:
            return {
                "messaging_product": "whatsapp",
                "contacts": [{"input": to_phone, "wa_id": to_phone}],
                "messages": [{"id": f"mock_wamid_{hash(to_phone + message)}"}],
            }

        if not self.access_token or not self.phone_number_id:
            raise ExternalServiceException(
                message="WhatsApp credentials are not configured",
                details={"service": "whatsapp"},
            )

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{self.base_url}/{self.phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if res.status_code != 200:
                raise ExternalServiceException(
                    message=f"WhatsApp API error: {res.text}",
                    status_code=res.status_code,
                    details={"response": res.text},
                )
            return res.json()
