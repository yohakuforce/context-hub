"""LLM adapter abstraction layer.

All LLM calls MUST go through this interface, never directly to a provider SDK.
This ensures that the provider (Claude / Antigravity / Codex) can be swapped
via the LLM_PROVIDER environment variable without touching business logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMMessage:
    """A single message in a conversation (user or assistant role)."""

    role: str   # "user" or "assistant"
    content: str


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM generation call."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int


class LLMAdapter(ABC):
    """Protocol for LLM text generation.

    Every provider adapter must implement this interface.
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response given a conversation history.

        Args:
            messages: Ordered list of user/assistant turns.
            system_prompt: Optional system instruction (passed as system role
                           where supported; prepended to messages otherwise).
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0.0 = deterministic).
            **kwargs: Provider-specific overrides.

        Returns:
            LLMResponse with generated content and token counts.
        """
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the underlying provider."""
        ...
