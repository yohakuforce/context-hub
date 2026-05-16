"""EmbeddingProvider protocol and shared value types.

All embedding implementations must satisfy this Protocol.
Business logic depends on this interface, not on concrete adapters.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from context_hub.shared.types import EmbeddingVector


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for generating dense embedding vectors from text."""

    async def embed(self, text: str) -> EmbeddingVector:
        """Embed a single text string and return an EmbeddingVector."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        """Embed multiple texts in a single batched call.

        Implementations should prefer batch processing for performance.
        Result order matches input order.
        """
        ...

    def model_name(self) -> str:
        """Human-readable name of the underlying embedding model."""
        ...

    def dimensions(self) -> int:
        """Number of dimensions in the output vector."""
        ...
