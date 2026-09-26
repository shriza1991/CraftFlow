"""Factory for AI/LLM Provider instantiation."""

from app.ai.base import LLMProvider
from app.ai.providers.mock_provider import MockLLMProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.config import get_settings
from app.core.exceptions import AIProviderException


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    """Instantiate and return the configured LLM provider instance."""
    settings = get_settings()
    name = (provider_name or settings.AI_PROVIDER).lower()

    if name == "mock":
        return MockLLMProvider()
    elif name == "openai":
        return OpenAIProvider()
    elif name in {"gemini", "anthropic"}:
        raise AIProviderException(
            message=f"Provider '{name}' adapter is stubbed for future milestone integration.",
            details={"provider": name},
        )
    else:
        raise AIProviderException(
            message=f"Unsupported AI provider: {name}",
            details={"provider": name},
        )
