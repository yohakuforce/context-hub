"""Tests for core.vectorstore — Protocol definitions and supporting types."""

from __future__ import annotations

import numpy as np
import pytest

from src.core.vectorstore import (
    HealthState,
    HealthStatus,
    MetaFilter,
    ScoredId,
    VectorStore,
)


# ---------------------------------------------------------------------------
# ScoredId
# ---------------------------------------------------------------------------


class TestScoredId:
    def test_attributes_are_accessible(self):
        item = ScoredId(doc_id="abc-123", score=0.85)
        assert item.doc_id == "abc-123"
        assert item.score == pytest.approx(0.85)

    def test_is_immutable(self):
        item = ScoredId(doc_id="x", score=0.5)
        with pytest.raises((AttributeError, TypeError)):
            item.score = 0.9  # type: ignore[misc]

    def test_equality(self):
        assert ScoredId("a", 0.1) == ScoredId("a", 0.1)
        assert ScoredId("a", 0.1) != ScoredId("b", 0.1)


# ---------------------------------------------------------------------------
# HealthStatus
# ---------------------------------------------------------------------------


class TestHealthStatus:
    def test_defaults(self):
        status = HealthStatus(state=HealthState.OK)
        assert status.state == HealthState.OK
        assert status.detail == ""

    def test_with_detail(self):
        status = HealthStatus(state=HealthState.DEGRADED, detail="slow index")
        assert status.detail == "slow index"

    def test_is_immutable(self):
        status = HealthStatus(state=HealthState.OK)
        with pytest.raises((AttributeError, TypeError)):
            status.state = HealthState.UNAVAILABLE  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HealthState enum
# ---------------------------------------------------------------------------


class TestHealthState:
    def test_values(self):
        assert HealthState.OK.value == "ok"
        assert HealthState.DEGRADED.value == "degraded"
        assert HealthState.UNAVAILABLE.value == "unavailable"

    def test_string_comparison(self):
        assert HealthState.OK == "ok"


# ---------------------------------------------------------------------------
# VectorStore Protocol runtime check
# ---------------------------------------------------------------------------


class _MinimalStore:
    """A minimal class that satisfies the VectorStore Protocol."""

    async def upsert(self, doc_id: str, embedding: np.ndarray, meta: dict) -> None:
        pass

    async def knn(self, query: np.ndarray, k: int, filter=None) -> list[ScoredId]:
        return []

    async def delete(self, doc_id: str) -> None:
        pass

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.OK)


class _IncompleteStore:
    """A class missing the health_check method."""

    async def upsert(self, doc_id: str, embedding: np.ndarray, meta: dict) -> None:
        pass

    async def knn(self, query: np.ndarray, k: int, filter=None) -> list[ScoredId]:
        return []

    async def delete(self, doc_id: str) -> None:
        pass


class TestVectorStoreProtocol:
    def test_minimal_store_satisfies_protocol(self):
        store = _MinimalStore()
        assert isinstance(store, VectorStore)

    def test_incomplete_store_does_not_satisfy_protocol(self):
        store = _IncompleteStore()
        assert not isinstance(store, VectorStore)

    def test_plain_object_does_not_satisfy_protocol(self):
        assert not isinstance(object(), VectorStore)
