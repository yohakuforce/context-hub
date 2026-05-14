"""BGE-M3 local embedding adapter.

Selected when EMBEDDING_PROVIDER=bge-m3.

Uses the FlagEmbedding library to run BAAI/bge-m3 locally.
Model is downloaded on first use and cached in the Hugging Face cache
directory (volume-mounted in Docker for persistence).

Requirements (added to Dockerfile):
  pip install FlagEmbedding sentence-transformers

BGE-M3 output:
  - Dense vector: 1024 dimensions (used here)
  - Sparse + multi-vector outputs available in future versions

Performance (CPU, Windows PC):
  ~50-150ms per text (500 tokens), ~30ms per text in batches of 12.

Reference: https://huggingface.co/BAAI/bge-m3
"""

from __future__ import annotations

import asyncio
import os
from functools import cached_property
from typing import Any

from src.infrastructure.embedding.base import EmbeddingProvider
from src.shared.types import EmbeddingVector

_MODEL_NAME = "BAAI/bge-m3"
_DIMENSIONS = 1024
_DEFAULT_BATCH_SIZE = 12
_DEFAULT_MAX_LENGTH = 8192


class BGEM3EmbeddingAdapter:
    """Embedding adapter backed by BGE-M3 running locally via FlagEmbedding.

    The model is loaded lazily on first use to keep startup time fast.
    All heavy computation runs in a thread-pool executor to avoid blocking
    the asyncio event loop.
    """

    def __init__(
        self,
        device: str | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        max_length: int = _DEFAULT_MAX_LENGTH,
        use_fp16: bool = True,
    ) -> None:
        # Device: "cpu" or "cuda". Falls back to env var EMBEDDING_DEVICE.
        self._device = device or os.environ.get("EMBEDDING_DEVICE", "cpu")
        self._batch_size = batch_size
        self._max_length = max_length
        self._use_fp16 = use_fp16
        self._model: Any = None  # lazy-loaded

    def _load_model(self) -> Any:
        """Load BGE-M3 model synchronously (called from thread pool)."""
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel  # type: ignore[import-untyped]
            self._model = BGEM3FlagModel(
                _MODEL_NAME,
                use_fp16=self._use_fp16,
            )
        return self._model

    async def embed(self, text: str) -> EmbeddingVector:
        """Embed a single text string."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        """Embed a batch of texts using BGE-M3 dense encoding.

        Runs in a thread pool to avoid blocking the event loop.
        """
        if not texts:
            return []

        loop = asyncio.get_event_loop()
        dense_vecs = await loop.run_in_executor(None, self._encode_sync, texts)

        return [
            EmbeddingVector(
                values=tuple(float(v) for v in vec),
                model_name=_MODEL_NAME,
                dimensions=_DIMENSIONS,
            )
            for vec in dense_vecs
        ]

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous encoding — called from thread pool executor."""
        model = self._load_model()
        result = model.encode(
            texts,
            batch_size=self._batch_size,
            max_length=self._max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return result["dense_vecs"].tolist()

    def model_name(self) -> str:
        return _MODEL_NAME

    def dimensions(self) -> int:
        return _DIMENSIONS
