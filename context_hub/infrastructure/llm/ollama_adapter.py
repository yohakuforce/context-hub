"""OllamaAdapter — HTTP call to a local Ollama server.

Selected when LLM_PROVIDER=ollama.

Ollama runs a local HTTP server (default: http://localhost:11434) that exposes
a generate endpoint compatible with common open-source models.

Configuration via environment variables:
  OLLAMA_BASE_URL  — default: http://localhost:11434
  OLLAMA_MODEL     — default: llama3

Documentation: https://ollama.com/docs/api
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from context_hub.infrastructure.llm.base import LLMAdapter, LLMMessage, LLMResponse

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"


class OllamaAdapter(LLMAdapter):
    """Adapter for local Ollama server (HTTP)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 180.0,
    ) -> None:
        self._base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self._model = model or os.environ.get("OLLAMA_MODEL", _DEFAULT_MODEL)
        self._timeout = timeout_seconds

    async def generate(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call Ollama /api/generate with the composed prompt."""
        prompt = _build_prompt(messages, system_prompt)
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                )
            except httpx.ConnectError as exc:
                raise RuntimeError(
                    f"Cannot connect to Ollama at {self._base_url}. "
                    "Is Ollama running? Start it with: ollama serve"
                ) from exc

        if response.status_code != 200:
            raise RuntimeError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        content = data.get("response", "")
        if not content:
            raise RuntimeError("Ollama returned empty response.")

        return LLMResponse(
            content=content.strip(),
            model=self._model,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

    def provider_name(self) -> str:
        return f"ollama:{self._model}"


def _build_prompt(messages: list[LLMMessage], system_prompt: str | None) -> str:
    parts: list[str] = []
    if system_prompt:
        parts.append(f"[SYSTEM]\n{system_prompt}\n")
    for msg in messages:
        role_label = "USER" if msg.role == "user" else "ASSISTANT"
        parts.append(f"[{role_label}]\n{msg.content}")
    return "\n\n".join(parts)
