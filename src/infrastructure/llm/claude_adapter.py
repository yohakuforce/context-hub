"""Claude (Anthropic) LLM adapter.

Uses anthropic Python SDK. Provider is selected when LLM_PROVIDER=claude.
"""

from __future__ import annotations

from typing import Any

import anthropic

from src.infrastructure.llm.base import LLMAdapter, LLMMessage, LLMResponse


class ClaudeAdapter(LLMAdapter):
    """Adapter for Claude API via the Anthropic SDK."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022") -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        anthropic_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
        }
        if system_prompt:
            create_kwargs["system"] = system_prompt
        # Note: Claude API does not expose temperature in all endpoints,
        # but include it for models that support it.
        create_kwargs["temperature"] = temperature
        create_kwargs.update(kwargs)

        response = await self._client.messages.create(**create_kwargs)

        content_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                content_text += block.text

        return LLMResponse(
            content=content_text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def provider_name(self) -> str:
        return f"claude:{self._model}"
