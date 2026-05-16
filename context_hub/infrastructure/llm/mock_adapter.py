"""Mock LLM adapter for testing and development without real API keys.

Use LLM_PROVIDER=mock in .env to activate this adapter locally.
This allows the full application stack to run without any API key.
"""

from __future__ import annotations

import json
from typing import Any

from context_hub.infrastructure.llm.base import LLMAdapter, LLMMessage, LLMResponse
from context_hub.shared.types import EmbeddingVector


class MockLLMAdapter(LLMAdapter):
    """Returns deterministic stub responses — safe for CI and key-free dev."""

    async def generate(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        last_user_content = ""
        for msg in reversed(messages):
            if msg.role == "user":
                last_user_content = msg.content[:50]
                break

        stub_content = json.dumps(
            {
                "summary": f"[MOCK] Summary of: {last_user_content}",
                "tags": ["mock", "test"],
                "entities": [],
                "language": "ja",
            },
            ensure_ascii=False,
        )
        return LLMResponse(
            content=stub_content,
            model="mock",
            input_tokens=len(last_user_content),
            output_tokens=len(stub_content),
        )

    def provider_name(self) -> str:
        return "mock"


class MockEmbeddingService:
    """Returns zero vectors — safe for CI and key-free dev."""

    DIMENSIONS = 1536

    async def embed(self, text: str) -> EmbeddingVector:
        values = tuple(0.0 for _ in range(self.DIMENSIONS))
        return EmbeddingVector(
            values=values,
            model_name="mock",
            dimensions=self.DIMENSIONS,
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        return [await self.embed(t) for t in texts]
