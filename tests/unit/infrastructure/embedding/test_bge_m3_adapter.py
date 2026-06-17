"""Unit tests for BGEM3EmbeddingAdapter.

FlagEmbedding / BGEM3FlagModel is mocked so tests run without the 2.3GB model.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from context_hub.infrastructure.embedding.bge_m3_adapter import (
    BGEM3EmbeddingAdapter,
    _DIMENSIONS,
    _MODEL_NAME,
)
from context_hub.shared.types import EmbeddingVector


def _make_mock_model(batch_size: int = 1) -> MagicMock:
    """Return a mock BGEM3FlagModel that produces zero vectors."""
    mock = MagicMock()
    mock.encode.return_value = {
        "dense_vecs": np.zeros((batch_size, _DIMENSIONS), dtype=np.float32)
    }
    return mock


class TestBGEM3EmbeddingAdapter:
    def test_model_name(self) -> None:
        adapter = BGEM3EmbeddingAdapter()
        assert adapter.model_name() == _MODEL_NAME

    def test_dimensions(self) -> None:
        adapter = BGEM3EmbeddingAdapter()
        assert adapter.dimensions() == _DIMENSIONS

    @pytest.mark.asyncio
    async def test_embed_returns_correct_dimensions(self) -> None:
        adapter = BGEM3EmbeddingAdapter()
        mock_model = _make_mock_model(batch_size=1)

        with patch.object(adapter, "_load_model", return_value=mock_model):
            vector = await adapter.embed("テストテキスト")

        assert isinstance(vector, EmbeddingVector)
        assert vector.dimensions == _DIMENSIONS
        assert len(vector.values) == _DIMENSIONS
        assert vector.model_name == _MODEL_NAME

    @pytest.mark.asyncio
    async def test_embed_batch_returns_list(self) -> None:
        adapter = BGEM3EmbeddingAdapter()
        texts = ["text one", "text two", "text three"]
        mock_model = _make_mock_model(batch_size=3)

        with patch.object(adapter, "_load_model", return_value=mock_model):
            vectors = await adapter.embed_batch(texts)

        assert len(vectors) == 3
        for vec in vectors:
            assert vec.dimensions == _DIMENSIONS

    @pytest.mark.asyncio
    async def test_embed_batch_empty_returns_empty(self) -> None:
        adapter = BGEM3EmbeddingAdapter()
        result = await adapter.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_encode_called_with_correct_args(self) -> None:
        adapter = BGEM3EmbeddingAdapter(batch_size=8, max_length=512)
        mock_model = _make_mock_model(batch_size=2)

        with patch.object(adapter, "_load_model", return_value=mock_model):
            await adapter.embed_batch(["hello", "world"])

        mock_model.encode.assert_called_once()
        call_kwargs = mock_model.encode.call_args
        assert call_kwargs[1]["batch_size"] == 8
        assert call_kwargs[1]["max_length"] == 512

    def test_lazy_model_load(self) -> None:
        """Model is None until _load_model is called."""
        adapter = BGEM3EmbeddingAdapter()
        assert adapter._model is None

    def test_encode_sync_calls_load_model(self) -> None:
        adapter = BGEM3EmbeddingAdapter()
        mock_model = _make_mock_model(batch_size=1)

        with patch.object(adapter, "_load_model", return_value=mock_model) as mock_load:
            adapter._encode_sync(["hello"])

        mock_load.assert_called_once()

    def test_fp16_disabled_on_cpu_by_default(self) -> None:
        """fp16 has no CPU kernel — must default off on the GPU-less Windows path."""
        adapter = BGEM3EmbeddingAdapter(device="cpu")
        assert adapter._use_fp16 is False

    def test_fp16_enabled_on_cuda_by_default(self) -> None:
        adapter = BGEM3EmbeddingAdapter(device="cuda")
        assert adapter._use_fp16 is True

    def test_explicit_use_fp16_overrides_device_default(self) -> None:
        assert BGEM3EmbeddingAdapter(device="cpu", use_fp16=True)._use_fp16 is True
        assert BGEM3EmbeddingAdapter(device="cuda", use_fp16=False)._use_fp16 is False

    def test_env_var_overrides_cpu_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMBEDDING_USE_FP16", "true")
        assert BGEM3EmbeddingAdapter(device="cpu")._use_fp16 is True
        monkeypatch.setenv("EMBEDDING_USE_FP16", "off")
        assert BGEM3EmbeddingAdapter(device="cuda")._use_fp16 is False
