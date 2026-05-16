"""Unit tests for IngestionService — batch_size and helper functions."""

from __future__ import annotations

import pytest

from src.application.ingestion_service import _batched, IngestionService
from src.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter


class TestBatched:
    def test_empty_list_yields_nothing(self):
        result = list(_batched([], 5))
        assert result == []

    def test_single_batch(self):
        result = list(_batched([1, 2, 3], 10))
        assert result == [[1, 2, 3]]

    def test_exact_multiple(self):
        result = list(_batched([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]

    def test_remainder_batch(self):
        result = list(_batched([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_batch_size_one(self):
        result = list(_batched([10, 20, 30], 1))
        assert result == [[10], [20], [30]]

    def test_preserves_order(self):
        items = list(range(100))
        batches = list(_batched(items, 7))
        reconstructed = [x for batch in batches for x in batch]
        assert reconstructed == items
