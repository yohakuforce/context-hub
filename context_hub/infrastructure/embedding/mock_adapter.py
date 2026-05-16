"""MockEmbeddingAdapter — deterministic embedding for tests and CI.

Returns a fixed-length zero vector (with a small hash-based perturbation
so different texts yield different vectors, making tests more realistic).
"""

from __future__ import annotations

import hashlib

from context_hub.infrastructure.embedding.base import EmbeddingProvider
from context_hub.shared.types import EmbeddingVector

_DIMENSIONS = 1024
_MODEL_NAME = "mock-embedding-v1"


class MockEmbeddingAdapter:
    """Deterministic fake embedding provider.

    Each text is hashed to produce a reproducible unit-norm-ish vector.
    Safe to use in unit tests and integration tests without GPU.
    """

    def model_name(self) -> str:
        return _MODEL_NAME

    def dimensions(self) -> int:
        return _DIMENSIONS

    async def embed(self, text: str) -> EmbeddingVector:
        values = _text_to_vector(text)
        return EmbeddingVector(
            values=values,
            model_name=_MODEL_NAME,
            dimensions=_DIMENSIONS,
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        return [await self.embed(t) for t in texts]


def _text_to_vector(text: str) -> tuple[float, ...]:
    """Hash text into a deterministic 1024-dim vector."""
    digest = hashlib.sha256(text.encode()).digest()
    # Expand 32 bytes → 1024 floats by repeating + cycling
    expanded: list[float] = []
    for i in range(_DIMENSIONS):
        byte_val = digest[i % len(digest)]
        # normalise to [-0.5, 0.5] so vectors are somewhat unit-norm
        expanded.append((byte_val / 255.0) - 0.5)
    return tuple(expanded)
