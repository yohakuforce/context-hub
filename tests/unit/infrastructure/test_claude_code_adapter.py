"""Unit tests for ClaudeCodeAdapter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_hub.infrastructure.llm.base import LLMMessage
from context_hub.infrastructure.llm.claude_code_adapter import (
    ClaudeCodeAdapter,
    _build_prompt,
    _run_claude_cli,
)


class TestBuildPrompt:
    def test_single_user_message(self) -> None:
        messages = [LLMMessage(role="user", content="Hello")]
        result = _build_prompt(messages, system_prompt=None)
        assert "[USER]" in result
        assert "Hello" in result

    def test_system_prompt_prepended(self) -> None:
        messages = [LLMMessage(role="user", content="Summarise this")]
        result = _build_prompt(messages, system_prompt="You are a helpful assistant.")
        assert "[SYSTEM]" in result
        assert "You are a helpful assistant." in result
        assert "[USER]" in result

    def test_assistant_message_labeled(self) -> None:
        messages = [
            LLMMessage(role="user", content="Question"),
            LLMMessage(role="assistant", content="Answer"),
        ]
        result = _build_prompt(messages, system_prompt=None)
        assert "[ASSISTANT]" in result

    def test_empty_messages_no_crash(self) -> None:
        result = _build_prompt([], system_prompt=None)
        assert result == ""

    def test_system_only_no_messages(self) -> None:
        result = _build_prompt([], system_prompt="System msg")
        assert "[SYSTEM]" in result
        assert "System msg" in result


class TestClaudeCodeAdapter:
    def test_provider_name(self) -> None:
        adapter = ClaudeCodeAdapter()
        assert adapter.provider_name() == "claude-code"

    def test_default_timeout(self) -> None:
        adapter = ClaudeCodeAdapter()
        assert adapter._timeout == 120.0

    def test_custom_timeout(self) -> None:
        adapter = ClaudeCodeAdapter(timeout_seconds=30.0)
        assert adapter._timeout == 30.0

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        """Successful subprocess execution returns LLMResponse."""
        adapter = ClaudeCodeAdapter(timeout_seconds=10.0)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"Generated content\n", b"")
        )

        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            response = await adapter.generate(
                messages=[LLMMessage(role="user", content="Hello")],
            )

        assert response.content == "Generated content"
        assert response.model == "claude-code-cli"

    @pytest.mark.asyncio
    async def test_generate_nonzero_exit_raises(self) -> None:
        """Non-zero exit code raises RuntimeError."""
        adapter = ClaudeCodeAdapter(timeout_seconds=10.0)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"some error"))

        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            with pytest.raises(RuntimeError, match="exited with code 1"):
                await adapter.generate(
                    messages=[LLMMessage(role="user", content="Hello")]
                )

    @pytest.mark.asyncio
    async def test_generate_empty_output_raises(self) -> None:
        """Empty stdout raises RuntimeError."""
        adapter = ClaudeCodeAdapter(timeout_seconds=10.0)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"   \n  ", b""))

        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            with pytest.raises(RuntimeError, match="empty output"):
                await adapter.generate(
                    messages=[LLMMessage(role="user", content="Hello")]
                )

    @pytest.mark.asyncio
    async def test_generate_cli_not_found_raises(self) -> None:
        """FileNotFoundError when CLI missing → RuntimeError with install hint."""
        adapter = ClaudeCodeAdapter(timeout_seconds=10.0)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("No such file: claude"),
        ):
            with pytest.raises(RuntimeError, match="claude CLI not found"):
                await adapter.generate(
                    messages=[LLMMessage(role="user", content="Hello")]
                )
