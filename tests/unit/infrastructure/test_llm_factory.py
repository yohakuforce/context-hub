"""Unit tests for LLM adapter factory (updated for 2026-05-15 policy)."""

import pytest

from context_hub.infrastructure.llm.factory import create_llm_adapter, create_embedding_service
from context_hub.infrastructure.llm.mock_adapter import MockLLMAdapter, MockEmbeddingService


class TestCreateLLMAdapterMock:
    def test_mock_provider_returns_mock_adapter(self) -> None:
        adapter = create_llm_adapter(provider="mock")
        assert isinstance(adapter, MockLLMAdapter)

    def test_mock_provider_name(self) -> None:
        adapter = create_llm_adapter(provider="mock")
        assert adapter.provider_name() == "mock"


class TestCreateLLMAdapterClaudeCode:
    def test_claude_code_returns_adapter(self) -> None:
        from context_hub.infrastructure.llm.claude_code_adapter import ClaudeCodeAdapter
        adapter = create_llm_adapter(provider="claude-code")
        assert isinstance(adapter, ClaudeCodeAdapter)

    def test_claude_code_provider_name(self) -> None:
        adapter = create_llm_adapter(provider="claude-code")
        assert adapter.provider_name() == "claude-code"

    def test_claude_code_custom_timeout(self) -> None:
        from context_hub.infrastructure.llm.claude_code_adapter import ClaudeCodeAdapter
        adapter = create_llm_adapter(provider="claude-code", claude_code_timeout=30.0)
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._timeout == 30.0


class TestCreateLLMAdapterCodex:
    def test_codex_returns_adapter(self) -> None:
        from context_hub.infrastructure.llm.codex_adapter import CodexAdapter
        adapter = create_llm_adapter(provider="codex")
        assert isinstance(adapter, CodexAdapter)

    def test_codex_provider_name(self) -> None:
        adapter = create_llm_adapter(provider="codex")
        assert adapter.provider_name() == "codex"


class TestCreateLLMAdapterOllama:
    def test_ollama_returns_adapter(self) -> None:
        from context_hub.infrastructure.llm.ollama_adapter import OllamaAdapter
        adapter = create_llm_adapter(provider="ollama")
        assert isinstance(adapter, OllamaAdapter)

    def test_ollama_provider_name_includes_model(self) -> None:
        adapter = create_llm_adapter(provider="ollama", ollama_model="llama3")
        assert "ollama" in adapter.provider_name()
        assert "llama3" in adapter.provider_name()


class TestDeprecatedProviders:
    def test_claude_api_raises_deprecation_error(self) -> None:
        with pytest.raises(ValueError, match="deprecated"):
            create_llm_adapter(provider="claude")

    def test_openai_api_raises_deprecation_error(self) -> None:
        with pytest.raises(ValueError, match="deprecated"):
            create_llm_adapter(provider="openai")

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            create_llm_adapter(provider="some_unknown_provider_xyz")


class TestCreateEmbeddingService:
    def test_mock_returns_mock_service(self) -> None:
        svc = create_embedding_service(provider="mock")
        assert isinstance(svc, MockEmbeddingService)

    def test_deprecated_openai_embedding_raises(self) -> None:
        with pytest.raises(ValueError, match="deprecated"):
            create_embedding_service(provider="openai")

    def test_deprecated_claude_embedding_raises(self) -> None:
        with pytest.raises(ValueError, match="deprecated"):
            create_embedding_service(provider="claude")

    def test_unknown_embedding_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
            create_embedding_service(provider="pinecone")


class TestMockLLMAdapter:
    @pytest.mark.asyncio
    async def test_generate_returns_response(self) -> None:
        from context_hub.infrastructure.llm.base import LLMMessage

        adapter = MockLLMAdapter()
        response = await adapter.generate(
            messages=[LLMMessage(role="user", content="Hello")]
        )
        assert response.content
        assert response.model == "mock"

    @pytest.mark.asyncio
    async def test_mock_embedding_returns_correct_dimensions(self) -> None:
        svc = MockEmbeddingService()
        vector = await svc.embed("test text")
        assert vector.dimensions == MockEmbeddingService.DIMENSIONS
        assert len(vector.values) == MockEmbeddingService.DIMENSIONS
        assert all(v == 0.0 for v in vector.values)

    @pytest.mark.asyncio
    async def test_mock_embedding_batch(self) -> None:
        svc = MockEmbeddingService()
        texts = ["text one", "text two", "text three"]
        vectors = await svc.embed_batch(texts)
        assert len(vectors) == 3
        for vec in vectors:
            assert vec.dimensions == MockEmbeddingService.DIMENSIONS
