"""ClaudeCodeAdapter — drives the Claude Code CLI via subprocess.

Selected when LLM_PROVIDER=claude-code.

This adapter requires that `claude` CLI is installed and authenticated on the
host machine (or Docker container) where Context-Hub runs.
Install: https://docs.anthropic.com/en/docs/claude-code

Usage:
  The CLI is invoked as:
      claude -p "<prompt text>"
  where -p means "print" mode (non-interactive, output to stdout).

  System prompt is prepended to the first user message as plain text because
  the Claude Code CLI does not have a dedicated --system flag in print mode.

Subprocess timeout:
  Default 120 s. Override via CLAUDE_CODE_TIMEOUT_SECONDS env var.

Error handling:
  - Non-zero exit code → raises RuntimeError with stderr content.
  - Timeout → raises TimeoutError.
  - Empty stdout → raises RuntimeError.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from context_hub.infrastructure.llm.base import LLMAdapter, LLMMessage, LLMResponse

# Environment variable name for subprocess timeout
_TIMEOUT_ENV = "CLAUDE_CODE_TIMEOUT_SECONDS"
_DEFAULT_TIMEOUT = 120.0


class ClaudeCodeAdapter(LLMAdapter):
    """Adapter for Claude Code CLI (subprocess call via `claude -p`)."""

    def __init__(self, timeout_seconds: float | None = None) -> None:
        self._timeout = timeout_seconds or float(
            os.environ.get(_TIMEOUT_ENV, _DEFAULT_TIMEOUT)
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        """Run `claude -p <prompt>` as a subprocess and return the output.

        The conversation is serialised as:
          [SYSTEM]\n<system_prompt>\n\n[USER]\n<last user message>

        Only the last user turn is passed because the CLI does not natively
        support multi-turn history in print mode. For multi-turn use cases
        the caller must concatenate prior turns into the system prompt or
        the final user message before calling this method.
        """
        prompt = _build_prompt(messages, system_prompt)
        stdout_text = await _run_claude_cli(prompt, self._timeout)

        return LLMResponse(
            content=stdout_text.strip(),
            model="claude-code-cli",
            # Token counts unavailable from CLI stdout — use 0 as placeholder
            input_tokens=0,
            output_tokens=0,
        )

    def provider_name(self) -> str:
        return "claude-code"


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_prompt(messages: list[LLMMessage], system_prompt: str | None) -> str:
    """Serialise messages to a flat string for the CLI -p argument."""
    parts: list[str] = []
    if system_prompt:
        parts.append(f"[SYSTEM]\n{system_prompt}\n")

    for msg in messages:
        role_label = "USER" if msg.role == "user" else "ASSISTANT"
        parts.append(f"[{role_label}]\n{msg.content}")

    return "\n\n".join(parts)


async def _run_claude_cli(prompt: str, timeout: float) -> str:
    """Execute `claude -p <prompt>` and return stdout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise TimeoutError(
                f"claude CLI timed out after {timeout}s. "
                "Increase CLAUDE_CODE_TIMEOUT_SECONDS or reduce prompt size."
            )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "claude CLI not found. Install it and ensure it is on PATH. "
            "See https://docs.anthropic.com/en/docs/claude-code"
        ) from exc

    if proc.returncode != 0:
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"claude CLI exited with code {proc.returncode}. "
            f"stderr: {stderr_text[:500]}"
        )

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    if not stdout_text.strip():
        raise RuntimeError("claude CLI returned empty output.")

    return stdout_text
