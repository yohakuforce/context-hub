"""Unit tests for CodexAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_hub.infrastructure.llm.base import LLMMessage
from context_hub.infrastructure.llm.codex_adapter import CodexAdapter, _build_prompt


class TestBuildPrompt:
    def test_single_user_message(self) -> None:
        messages = [LLMMessage(role="user", content="Write tests")]
        result = _build_prompt(messages, system_prompt=None)
        assert "[USER]" in result
        assert "Write tests" in result

    def test_system_prompt_included(self) -> None:
        messages = [LLMMessage(role="user", content="Hello")]
        result = _build_prompt(messages, system_prompt="Be concise.")
        assert "[SYSTEM]" in result
        assert "Be concise." in result


class TestCodexAdapter:
    def test_provider_name(self) -> None:
        adapter = CodexAdapter()
        assert adapter.provider_name() == "codex"

    def test_default_timeout(self) -> None:
        adapter = CodexAdapter()
        assert adapter._timeout == 120.0

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        adapter = CodexAdapter(timeout_seconds=10.0)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"Codex output\n", b""))

        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            response = await adapter.generate(
                messages=[LLMMessage(role="user", content="Hello")]
            )

        assert response.content == "Codex output"
        assert response.model == "codex-cli"

    @pytest.mark.asyncio
    async def test_generate_nonzero_exit_raises(self) -> None:
        adapter = CodexAdapter(timeout_seconds=10.0)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error msg"))

        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            with pytest.raises(RuntimeError, match="exited with code 1"):
                await adapter.generate(
                    messages=[LLMMessage(role="user", content="Hello")]
                )

    @pytest.mark.asyncio
    async def test_generate_cli_not_found_raises(self) -> None:
        adapter = CodexAdapter(timeout_seconds=10.0)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("No such file: codex"),
        ):
            with pytest.raises(RuntimeError, match="codex CLI not found"):
                await adapter.generate(
                    messages=[LLMMessage(role="user", content="Hello")]
                )
