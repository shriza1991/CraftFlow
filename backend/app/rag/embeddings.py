"""Embedding provider abstraction and implementations (Mock and OpenAI)."""

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import AIProviderException, RAGException
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class EmbeddingProvider(ABC):
    """Abstract interface for text embedding providers."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the vector dimensionality."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate vector embedding for a single text string."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate vector embeddings for a list of text strings."""
        pass


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic, offline embedding generator for testing and local development.

    Uses word-hash accumulation and unit-normalization so that texts sharing key terms
    have high cosine similarity, while being 100% deterministic and offline.
    """

    def __init__(self, dimension: int | None = None):
        self._dim = dimension or settings.EMBEDDING_DIMENSION

    @property
    def dimension(self) -> int:
        return self._dim

    def _embed(self, text: str) -> list[float]:
        cleaned = text.strip().lower()
        if not cleaned:
            return [0.0] * self._dim

        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "is",
            "are",
            "was",
            "were",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "it",
            "this",
            "that",
            "what",
            "how",
            "when",
            "where",
            "who",
            "which",
            "why",
            "can",
            "should",
            "could",
            "would",
            "i",
            "you",
            "my",
            "your",
            "we",
            "our",
        }
        all_words = re.findall(r"\w+", cleaned)
        content_words = [w for w in all_words if w not in stopwords]
        words = content_words if content_words else all_words

        if not words:
            return [0.0] * self._dim

        vector = [0.0] * self._dim
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            for i in range(16):
                idx = int.from_bytes(digest[i * 2 : i * 2 + 2], "big") % self._dim
                val = (digest[i] - 128) / 128.0
                vector[idx] += val

        # Normalize to unit length (L2 norm)
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0.0:
            return [round(x / norm, 6) for x in vector]
        return [0.0] * self._dim

    def embed_text(self, text: str) -> list[float]:
        return self._embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Real OpenAI embedding provider using text-embedding-3-small/large."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
    ):
        self._api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self._model = model or settings.OPENAI_EMBEDDING_MODEL
        self._dim = dimension or settings.EMBEDDING_DIMENSION

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_text(self, text: str) -> list[float]:
        res = self.embed_batch([text])
        if not res:
            raise RAGException("OpenAI embedding API returned empty results.")
        return res[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise AIProviderException(
                message="OPENAI_API_KEY is not configured for OpenAI embeddings.",
                details={"provider": "openai"},
            )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
            "dimensions": self._dim,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers=headers,
                    json=payload,
                )
                if response.status_code != 200:
                    raise AIProviderException(
                        message=f"OpenAI embedding request failed: {response.text}",
                        details={"status_code": response.status_code},
                    )
                data = response.json()
                embeddings = [item["embedding"] for item in data["data"]]
                for emb in embeddings:
                    if len(emb) != self._dim:
                        raise RAGException(
                            message=f"Embedding dimension mismatch: expected {self._dim}, got {len(emb)}",
                            details={"expected": self._dim, "received": len(emb)},
                        )
                return embeddings
        except AIProviderException:
            raise
        except Exception as exc:
            raise RAGException(
                message=f"Failed to generate embeddings from OpenAI: {exc!s}",
                details={"error": str(exc)},
            ) from exc


def get_embedding_provider() -> EmbeddingProvider:
    """Factory function returning the configured EmbeddingProvider."""
    provider_name = settings.EMBEDDING_PROVIDER.lower().strip()
    if provider_name == "openai":
        return OpenAIEmbeddingProvider()
    return MockEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
