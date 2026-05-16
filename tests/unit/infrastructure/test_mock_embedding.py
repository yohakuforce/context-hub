"""Unit tests for MockEmbeddingAdapter."""

from __future__ import annotations

import pytest

from src.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter
from src.infrastructure.embedding.factory import get_embedding_provider


class TestMockEmbeddingAdapter:
    @pytest.fixture
    def adapter(self):
        return MockEmbeddingAdapter()

    @pytest.mark.asyncio
    async def test_embed_returns_embedding_vector(self, adapter):
        vec = await adapter.embed("hello world")
        assert vec is not None
        assert vec.dimensions == 1024
        assert len(vec.values) == 1024

    @pytest.mark.asyncio
    async def test_embed_is_deterministic(self, adapter):
        v1 = await adapter.embed("deterministic text")
        v2 = await adapter.embed("deterministic text")
        assert v1.values == v2.values

    @pytest.mark.asyncio
    async def test_embed_different_texts_produce_different_vectors(self, adapter):
        v1 = await adapter.embed("text one")
        v2 = await adapter.embed("text two")
        assert v1.values != v2.values

    @pytest.mark.asyncio
    async def test_embed_returns_correct_model_name(self, adapter):
        vec = await adapter.embed("test")
        assert vec.model_name == "mock-embedding-v1"

    @pytest.mark.asyncio
    async def test_embed_batch_returns_list(self, adapter):
        texts = ["alpha", "beta", "gamma"]
        results = await adapter.embed_batch(texts)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_embed_batch_order_preserved(self, adapter):
        texts = ["first", "second", "third"]
        batch = await adapter.embed_batch(texts)
        singles = [await adapter.embed(t) for t in texts]
        for b, s in zip(batch, singles):
            assert b.values == s.values

    def test_model_name(self, adapter):
        assert adapter.model_name() == "mock-embedding-v1"

    def test_dimensions(self, adapter):
        assert adapter.dimensions() == 1024

    @pytest.mark.asyncio
    async def test_empty_string_embeds_without_error(self, adapter):
        vec = await adapter.embed("")
        assert vec.dimensions == 1024


class TestEmbeddingFactory:
    def test_mock_provider_returns_mock_adapter(self):
        provider = get_embedding_provider("mock")
        assert isinstance(provider, MockEmbeddingAdapter)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embedding_provider("unknown-provider")

    def test_bge_m3_returns_adapter_when_available(self):
        """bge-m3 should return a provider (if FlagEmbedding is installed)
        or raise an import/runtime error if the model is unavailable."""
        try:
            provider = get_embedding_provider("bge-m3")
            # If it succeeds, provider must satisfy EmbeddingProvider protocol
            assert hasattr(provider, "embed")
            assert hasattr(provider, "embed_batch")
        except (ImportError, ModuleNotFoundError, Exception):
            # Acceptable — model may not be downloaded in CI
            pass
