"""OpenAI LLM adapter.

Used for both text generation (GPT-4o) and embeddings (text-embedding-3-small).
Selected when LLM_PROVIDER=openai.
"""

from __future__ import annotations

from typing import Any

import openai

from src.infrastructure.llm.base import LLMAdapter, LLMMessage, LLMResponse
from src.shared.types import EmbeddingVector

# Default embedding model per tech-stack.md
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536


class OpenAIAdapter(LLMAdapter):
    """Adapter for OpenAI GPT-4o text generation."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        openai_messages: list[dict[str, str]] = []
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            openai_messages.append({"role": msg.role, "content": msg.content})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )

    def provider_name(self) -> str:
        return f"openai:{self._model}"


class OpenAIEmbeddingService:
    """Standalone embedding service backed by OpenAI.

    Separate from the LLMAdapter because embedding is not a chat-generation
    operation and has a distinct interface.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._dimensions = dimensions

    async def embed(self, text: str) -> EmbeddingVector:
        """Generate an embedding vector for the given text."""
        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
        )
        values = tuple(response.data[0].embedding)
        return EmbeddingVector(
            values=values,
            model_name=self._model,
            dimensions=len(values),
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        """Generate embedding vectors for a batch of texts."""
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        # Results are returned in the same order as input
        return [
            EmbeddingVector(
                values=tuple(item.embedding),
                model_name=self._model,
                dimensions=len(item.embedding),
            )
            for item in response.data
        ]
