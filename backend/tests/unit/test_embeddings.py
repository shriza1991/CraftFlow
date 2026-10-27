"""Unit tests for embedding providers."""

import pytest
from app.core.exceptions import AIProviderException
from app.rag.embeddings import (
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)


def test_mock_embedding_provider_dimension():
    provider = MockEmbeddingProvider(dimension=1536)
    assert provider.dimension == 1536
    vec = provider.embed_text("Luxury bathtub in Carrara marble")
    assert len(vec) == 1536


def test_mock_embedding_provider_deterministic():
    provider = MockEmbeddingProvider(dimension=768)
    text = "Nero Marquina is a black marble from Spain."
    vec1 = provider.embed_text(text)
    vec2 = provider.embed_text(text)
    assert vec1 == vec2


def test_mock_embedding_provider_batch():
    provider = MockEmbeddingProvider(dimension=512)
    texts = [
        "Travertine fluted tub",
        "Calacatta Viola heritage soaking tub",
        "Verde Alpi serpentinite basin",
    ]
    vectors = provider.embed_batch(texts)
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 512


def test_mock_embedding_empty_text():
    provider = MockEmbeddingProvider(dimension=128)
    vec = provider.embed_text("")
    assert len(vec) == 128
    assert all(x == 0.0 for x in vec)


def test_get_embedding_provider_factory():
    provider = get_embedding_provider()
    assert isinstance(provider, MockEmbeddingProvider)
    assert provider.dimension == 1536


def test_openai_provider_missing_key_raises():
    provider = OpenAIEmbeddingProvider(api_key="")
    with pytest.raises(AIProviderException) as exc:
        provider.embed_text("Test query")
    assert "OPENAI_API_KEY" in str(exc.value.message)
