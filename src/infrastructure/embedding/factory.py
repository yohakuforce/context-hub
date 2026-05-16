"""EmbeddingProvider factory.

Selects the correct EmbeddingProvider based on EMBEDDING_PROVIDER env var.

Supported values:
  bge-m3  — BGEM3EmbeddingAdapter  (requires FlagEmbedding + GPU/CPU)
  mock    — MockEmbeddingAdapter   (CI / key-free development)
"""

from __future__ import annotations

from src.infrastructure.embedding.base import EmbeddingProvider


def get_embedding_provider(provider_name: str = "mock") -> EmbeddingProvider:
    """Return an EmbeddingProvider instance for the given *provider_name*.

    Args:
        provider_name: One of "bge-m3" or "mock".

    Raises:
        ValueError: If an unknown provider name is given.
    """
    match provider_name:
        case "bge-m3":
            from src.infrastructure.embedding.bge_m3_adapter import (
                BGEM3EmbeddingAdapter,
            )
            return BGEM3EmbeddingAdapter()  # type: ignore[return-value]
        case "mock":
            from src.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter
            return MockEmbeddingAdapter()  # type: ignore[return-value]
        case _:
            raise ValueError(
                f"Unknown embedding provider: '{provider_name}'. "
                "Valid values: 'bge-m3', 'mock'."
            )
