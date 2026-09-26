"""OpenAI Provider implementation using async HTTP client."""

from typing import Any

import httpx

from app.ai.base import LLMMessage, LLMProvider, LLMResponse
from app.core.config import get_settings
from app.core.exceptions import AIProviderException
from app.core.logging import get_logger

logger = get_logger(__name__)


class OpenAIProvider(LLMProvider):
    """Production-ready provider for OpenAI Chat & Embedding APIs."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        embedding_model: str | None = None,
        base_url: str = "https://api.openai.com/v1",
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.embedding_model = embedding_model or settings.OPENAI_EMBEDDING_MODEL
        self.base_url = base_url.rstrip("/")

    def _ensure_authenticated(self) -> None:
        if not self.api_key:
            raise AIProviderException(
                message="OpenAI API key is not configured. Set OPENAI_API_KEY or use MockLLMProvider.",
                details={"provider": "openai"},
            )

    async def generate(
        self,
        messages: list[LLMMessage | dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self._ensure_authenticated()

        formatted_messages = []
        for msg in messages:
            if isinstance(msg, LLMMessage):
                formatted_messages.append(msg.model_dump(exclude_none=True))
            else:
                formatted_messages.append(msg)

        payload: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": formatted_messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                if response.status_code != 200:
                    raise AIProviderException(
                        message=f"OpenAI API call failed with status {response.status_code}",
                        details={"response": response.text, "status_code": response.status_code},
                    )
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return LLMResponse(
                    content=content,
                    model=data.get("model", self.model),
                    usage=usage,
                    raw=data,
                )
        except httpx.RequestError as exc:
            raise AIProviderException(
                message=f"Network error communicating with OpenAI: {exc!s}",
                details={"error": str(exc)},
            ) from exc

    async def embed(
        self,
        texts: list[str],
        **kwargs: Any,
    ) -> list[list[float]]:
        self._ensure_authenticated()

        payload = {
            "model": kwargs.get("model", self.embedding_model),
            "input": texts,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers=headers,
                )
                if response.status_code != 200:
                    raise AIProviderException(
                        message=f"OpenAI Embedding API call failed with status {response.status_code}",
                        details={"response": response.text, "status_code": response.status_code},
                    )
                data = response.json()
                return [item["embedding"] for item in data["data"]]
        except httpx.RequestError as exc:
            raise AIProviderException(
                message=f"Network error communicating with OpenAI Embeddings: {exc!s}",
                details={"error": str(exc)},
            ) from exc
