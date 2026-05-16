"""Tests for SqliteVecStore — VectorStore Protocol implementation.

All tests use a temporary file-backed SQLite database (not :memory:) because
each open_connection() call opens a new connection.  With :memory:, each new
connection gets a blank database; we need persistence across calls.

Covers:
- upsert + knn basic flow
- delete removes embedding
- health_check returns OK
- knn with metadata filter
- dimension validation
- Protocol isinstance check
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest
import sqlite_vec

from src.adapters.sqlite.migration_runner import SqliteMigrationRunner
from src.adapters.sqlite.vec_store import SqliteVecStore, _EMBEDDING_DIM
from src.core.vectorstore import HealthState, VectorStore


def _make_vec(dim: int = _EMBEDDING_DIM, fill: float = 0.0) -> np.ndarray:
    """Return a unit-normalised random vector of the given dimension."""
    vec = np.random.default_rng(42).random(dim).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    return vec


def _unit(values: list[float]) -> np.ndarray:
    arr = np.array(values, dtype=np.float32)
    return arr / np.linalg.norm(arr)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Return a path to an initialised SQLite database."""
    path = str(tmp_path / "vec_test.db")
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    schema_path = (
        Path(__file__).parent.parent.parent.parent.parent
        / "schema" / "sqlite" / "001_init.sql"
    )
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.close()
    return path


@pytest.mark.asyncio
class TestSqliteVecStore:
    async def test_health_check_returns_ok(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        status = await store.health_check()
        assert status.state == HealthState.OK

    async def test_upsert_and_knn_returns_result(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        vec = _make_vec()
        await store.upsert("doc-1", vec, {})
        results = await store.knn(vec, k=1)
        assert len(results) == 1
        assert results[0].doc_id == "doc-1"

    async def test_knn_score_is_in_unit_interval(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        vec = _make_vec()
        await store.upsert("doc-1", vec, {})
        results = await store.knn(vec, k=1)
        score = results[0].score
        assert 0.0 <= score <= 1.0

    async def test_knn_identical_vector_scores_near_one(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        vec = _make_vec()
        await store.upsert("doc-1", vec, {})
        results = await store.knn(vec, k=1)
        assert results[0].score > 0.99

    async def test_knn_ranking_by_similarity(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        # doc-close shares components with query; doc-far is orthogonal
        base = _unit([1.0] + [0.0] * (_EMBEDDING_DIM - 1))
        close = _unit([0.9, 0.1] + [0.0] * (_EMBEDDING_DIM - 2))
        far = _unit([0.0, 1.0] + [0.0] * (_EMBEDDING_DIM - 2))
        await store.upsert("doc-close", close, {})
        await store.upsert("doc-far", far, {})
        results = await store.knn(base, k=2)
        ids = [r.doc_id for r in results]
        assert ids[0] == "doc-close"

    async def test_knn_respects_k_limit(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        for i in range(5):
            await store.upsert(f"doc-{i}", _make_vec(), {})
        results = await store.knn(_make_vec(), k=3)
        assert len(results) <= 3

    async def test_delete_removes_document(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        vec = _make_vec()
        await store.upsert("doc-to-delete", vec, {})
        await store.delete("doc-to-delete")
        results = await store.knn(vec, k=5)
        ids = [r.doc_id for r in results]
        assert "doc-to-delete" not in ids

    async def test_delete_nonexistent_is_noop(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        await store.delete("doc-not-exist")  # must not raise

    async def test_upsert_replaces_existing(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        original = _unit([1.0] + [0.0] * (_EMBEDDING_DIM - 1))
        updated = _unit([0.0, 1.0] + [0.0] * (_EMBEDDING_DIM - 2))
        await store.upsert("doc-1", original, {"version": "1"})
        await store.upsert("doc-1", updated, {"version": "2"})
        results = await store.knn(updated, k=1)
        assert results[0].doc_id == "doc-1"
        assert results[0].score > 0.99

    async def test_dimension_validation_raises(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        bad = np.zeros(512, dtype=np.float32)
        with pytest.raises(ValueError, match="dimension"):
            await store.upsert("doc-bad", bad, {})

    async def test_knn_dimension_validation_raises(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        bad = np.zeros(512, dtype=np.float32)
        with pytest.raises(ValueError, match="dimension"):
            await store.knn(bad, k=5)

    async def test_knn_with_metadata_filter(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        base = _unit([1.0] + [0.0] * (_EMBEDDING_DIM - 1))
        vec_a = _unit([0.99, 0.01] + [0.0] * (_EMBEDDING_DIM - 2))
        vec_b = _unit([0.01, 0.99] + [0.0] * (_EMBEDDING_DIM - 2))
        await store.upsert("doc-a", vec_a, {"project_id": "proj-1"})
        await store.upsert("doc-b", vec_b, {"project_id": "proj-2"})
        results = await store.knn(base, k=5, filter={"project_id": "proj-1"})
        ids = [r.doc_id for r in results]
        assert "doc-a" in ids
        assert "doc-b" not in ids

    async def test_knn_empty_store_returns_empty(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        results = await store.knn(_make_vec(), k=5)
        assert results == []

    async def test_satisfies_vector_store_protocol(self, db_path: str) -> None:
        store = SqliteVecStore(db_path)
        assert isinstance(store, VectorStore)

    async def test_health_check_on_invalid_path_returns_unavailable(self) -> None:
        store = SqliteVecStore("/nonexistent/path/to/db.sqlite")
        status = await store.health_check()
        assert status.state == HealthState.UNAVAILABLE
