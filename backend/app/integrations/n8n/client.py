"""n8n Webhook Client for triggering external automation workflows."""

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import ExternalServiceException
from app.integrations.base import ExternalClient


class N8nWebhookClient(ExternalClient):
    """Client for triggering inbound n8n automation workflows securely."""

    def __init__(
        self, base_url: str | None = None, secret: str | None = None, is_mock: bool = True
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.N8N_BASE_URL).rstrip("/")
        self.secret = secret or settings.N8N_WEBHOOK_SECRET
        self.is_mock = is_mock

    async def ping(self) -> bool:
        return True

    async def trigger_workflow(self, webhook_path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Trigger an n8n webhook workflow with JSON payload."""
        if self.is_mock:
            return {"status": "dispatched", "workflow": webhook_path, "mock": True}

        url = f"{self.base_url}/{webhook_path.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Secret": self.secret,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code not in {200, 201, 202}:
                    raise ExternalServiceException(
                        message=f"n8n webhook error with status {res.status_code}",
                        status_code=res.status_code,
                        details={"response": res.text},
                    )
                return (
                    res.json()
                    if res.headers.get("content-type") == "application/json"
                    else {"status": "ok"}
                )
        except httpx.RequestError as exc:
            raise ExternalServiceException(
                message=f"Failed to reach n8n server: {exc!s}",
                details={"url": url, "error": str(exc)},
            ) from exc
