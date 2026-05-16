"""Unit tests for OllamaAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_hub.infrastructure.llm.base import LLMMessage
from context_hub.infrastructure.llm.ollama_adapter import OllamaAdapter, _build_prompt


class TestBuildPrompt:
    def test_system_and_user(self) -> None:
        messages = [LLMMessage(role="user", content="Question")]
        result = _build_prompt(messages, system_prompt="System context")
        assert "[SYSTEM]" in result
        assert "[USER]" in result

    def test_no_system(self) -> None:
        messages = [LLMMessage(role="user", content="Q")]
        result = _build_prompt(messages, system_prompt=None)
        assert "[SYSTEM]" not in result
        assert "[USER]" in result


class TestOllamaAdapter:
    def test_provider_name_includes_model(self) -> None:
        adapter = OllamaAdapter(model="mistral")
        assert "ollama" in adapter.provider_name()
        assert "mistral" in adapter.provider_name()

    def test_default_model(self) -> None:
        adapter = OllamaAdapter()
        assert adapter._model == "llama3"

    def test_custom_base_url(self) -> None:
        adapter = OllamaAdapter(base_url="http://my-server:11434")
        assert adapter._base_url == "http://my-server:11434"

    def test_trailing_slash_stripped(self) -> None:
        adapter = OllamaAdapter(base_url="http://localhost:11434/")
        assert not adapter._base_url.endswith("/")

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        adapter = OllamaAdapter(timeout_seconds=5.0)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Ollama says hi",
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            response = await adapter.generate(
                messages=[LLMMessage(role="user", content="Hello")]
            )

        assert response.content == "Ollama says hi"
        assert response.input_tokens == 10
        assert response.output_tokens == 5

    @pytest.mark.asyncio
    async def test_generate_non_200_raises(self) -> None:
        adapter = OllamaAdapter()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                await adapter.generate(
                    messages=[LLMMessage(role="user", content="Hello")]
                )
