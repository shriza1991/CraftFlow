"""Unit tests for AI provider abstraction and mock implementation."""

import pytest
from app.ai.base import LLMMessage
from app.ai.factory import get_llm_provider
from app.ai.providers.mock_provider import MockLLMProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.exceptions import AIProviderException


@pytest.mark.asyncio
async def test_mock_llm_provider():
    """Verify MockLLMProvider produces deterministic replies offline."""
    provider = MockLLMProvider(default_reply="Luxury marble bathtub response")
    messages = [LLMMessage(role="user", content="Tell me about your bathtubs.")]

    response = await provider.generate(messages)
    assert response.content == "Luxury marble bathtub response"
    assert response.model == "mock-gpt-model"
    assert response.usage["total_tokens"] > 0
    assert len(provider.history) == 1


@pytest.mark.asyncio
async def test_mock_llm_embeddings():
    """Verify mock provider generates deterministic embeddings."""
    provider = MockLLMProvider(embedding_dim=128)
    vectors = await provider.embed(["Carved marble tub", "Stone basin"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 128
    assert len(vectors[1]) == 128


def test_ai_provider_factory():
    """Verify factory returns appropriate provider instance."""
    mock_p = get_llm_provider("mock")
    assert isinstance(mock_p, MockLLMProvider)

    with pytest.raises(AIProviderException):
        get_llm_provider("unsupported_vendor")


@pytest.mark.asyncio
async def test_openai_unauthenticated_fails_safely():
    """Verify OpenAI provider safely raises AIProviderException when key is missing."""
    provider = OpenAIProvider(api_key="")
    with pytest.raises(AIProviderException) as exc_info:
        await provider.generate([LLMMessage(role="user", content="Hello")])
    assert "OpenAI API key is not configured" in exc_info.value.message
