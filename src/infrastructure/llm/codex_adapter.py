"""CodexAdapter — drives the Codex CLI via subprocess.

Selected when LLM_PROVIDER=codex.

This adapter requires that `codex` CLI is installed and authenticated on the
host machine where Context-Hub runs.

The Codex CLI is invoked in quiet / non-interactive mode:
    codex -q "<prompt>"

Subprocess timeout:
  Default 120 s. Override via CODEX_TIMEOUT_SECONDS env var.

Error handling:
  - Non-zero exit code → raises RuntimeError with stderr content.
  - Timeout → raises TimeoutError.
  - Missing CLI → raises RuntimeError with installation hint.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from src.infrastructure.llm.base import LLMAdapter, LLMMessage, LLMResponse

_TIMEOUT_ENV = "CODEX_TIMEOUT_SECONDS"
_DEFAULT_TIMEOUT = 120.0


class CodexAdapter(LLMAdapter):
    """Adapter for Codex CLI (subprocess call via `codex -q`)."""

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
        """Run `codex -q <prompt>` as a subprocess and return the output."""
        prompt = _build_prompt(messages, system_prompt)
        stdout_text = await _run_codex_cli(prompt, self._timeout)

        return LLMResponse(
            content=stdout_text.strip(),
            model="codex-cli",
            input_tokens=0,
            output_tokens=0,
        )

    def provider_name(self) -> str:
        return "codex"


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_prompt(messages: list[LLMMessage], system_prompt: str | None) -> str:
    parts: list[str] = []
    if system_prompt:
        parts.append(f"[SYSTEM]\n{system_prompt}\n")
    for msg in messages:
        role_label = "USER" if msg.role == "user" else "ASSISTANT"
        parts.append(f"[{role_label}]\n{msg.content}")
    return "\n\n".join(parts)


async def _run_codex_cli(prompt: str, timeout: float) -> str:
    """Execute `codex -q <prompt>` and return stdout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "codex",
            "-q",
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
                f"codex CLI timed out after {timeout}s. "
                "Increase CODEX_TIMEOUT_SECONDS or reduce prompt size."
            )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "codex CLI not found. Install the Codex CLI and ensure it is on PATH."
        ) from exc

    if proc.returncode != 0:
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"codex CLI exited with code {proc.returncode}. "
            f"stderr: {stderr_text[:500]}"
        )

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    if not stdout_text.strip():
        raise RuntimeError("codex CLI returned empty output.")

    return stdout_text
