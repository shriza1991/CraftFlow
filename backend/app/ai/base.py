"""Abstract Base Classes and Data Contracts for AI/LLM Providers."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """Standard message representation for chat completions."""

    role: str = Field(..., description="Message author role: system, user, assistant, tool")
    content: str = Field(..., description="Text content of the message")
    name: str | None = Field(default=None, description="Optional name of the sender/tool")


class LLMResponse(BaseModel):
    """Standardized response from any LLM provider."""

    content: str = Field(..., description="Generated text response from the model")
    model: str = Field(..., description="The specific model that generated the completion")
    usage: dict[str, int] = Field(
        default_factory=dict,
        description="Token usage metrics (prompt_tokens, completion_tokens, total_tokens)",
    )
    raw: Any = Field(default=None, description="Optional raw provider-specific response object")


class LLMProvider(ABC):
    """Abstract interface that all LLM providers must implement."""

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage | dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response given a list of conversation messages."""
        pass

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        **kwargs: Any,
    ) -> list[list[float]]:
        """Generate vector embeddings for input texts."""
        pass
