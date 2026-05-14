"""Unit tests for LLM adapter factory."""

import pytest

from src.infrastructure.llm.factory import create_llm_adapter, create_embedding_service
from src.infrastructure.llm.mock_adapter import MockLLMAdapter, MockEmbeddingService


class TestCreateLLMAdapter:
    def test_mock_provider_returns_mock_adapter(self):
        adapter = create_llm_adapter(provider="mock")
        assert isinstance(adapter, MockLLMAdapter)

    def test_mock_provider_name(self):
        adapter = create_llm_adapter(provider="mock")
        assert adapter.provider_name() == "mock"

    def test_claude_without_key_raises(self):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            create_llm_adapter(provider="claude")

    def test_openai_without_key_raises(self):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            create_llm_adapter(provider="openai")

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            create_llm_adapter(provider="antigravity_v99")


class TestCreateEmbeddingService:
    def test_mock_returns_mock_service(self):
        svc = create_embedding_service(provider="mock")
        assert isinstance(svc, MockEmbeddingService)

    def test_claude_without_openai_key_raises(self):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            create_embedding_service(provider="claude")


class TestMockLLMAdapter:
    @pytest.mark.asyncio
    async def test_generate_returns_response(self):
        from src.infrastructure.llm.base import LLMMessage

        adapter = MockLLMAdapter()
        response = await adapter.generate(
            messages=[LLMMessage(role="user", content="Hello")]
        )
        assert response.content
        assert response.model == "mock"

    @pytest.mark.asyncio
    async def test_mock_embedding_returns_correct_dimensions(self):
        svc = MockEmbeddingService()
        vector = await svc.embed("test text")
        assert vector.dimensions == MockEmbeddingService.DIMENSIONS
        assert len(vector.values) == MockEmbeddingService.DIMENSIONS
        assert all(v == 0.0 for v in vector.values)
