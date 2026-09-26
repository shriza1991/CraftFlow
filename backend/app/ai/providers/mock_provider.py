"""Mock LLM Provider for deterministic testing and offline development."""

from typing import Any

from app.ai.base import LLMMessage, LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider requiring zero external network calls or credentials."""

    def __init__(
        self,
        default_reply: str = "This is a deterministic mock response from the Ages Art AI system.",
        embedding_dim: int = 1536,
    ):
        self.default_reply = default_reply
        self.embedding_dim = embedding_dim
        self.history: list[list[LLMMessage | dict[str, Any]]] = []

    async def generate(
        self,
        messages: list[LLMMessage | dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Return a predictable mock completion and record interaction."""
        self.history.append(messages)

        # Allow dynamic override through kwargs for tests
        custom_reply = kwargs.get("mock_response", self.default_reply)

        return LLMResponse(
            content=custom_reply,
            model="mock-gpt-model",
            usage={
                "prompt_tokens": sum(len(str(m)) for m in messages),
                "completion_tokens": len(custom_reply),
                "total_tokens": sum(len(str(m)) for m in messages) + len(custom_reply),
            },
            raw={"provider": "mock", "temperature": temperature},
        )

    async def embed(
        self,
        texts: list[str],
        **kwargs: Any,
    ) -> list[list[float]]:
        """Return deterministic dummy vector representations."""
        results = []
        for text in texts:
            # Deterministic hash-based pseudo vector
            seed = sum(ord(c) for c in text) % 1000
            val = seed / 1000.0
            vector = [val] * self.embedding_dim
            results.append(vector)
        return results
