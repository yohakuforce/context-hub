"""SQLite-vec implementation of the VectorStore Protocol.

Uses the sqlite-vec extension to store and query 1024-dimensional float32
embeddings in a vec0 virtual table.  All I/O is performed in a thread pool
via asyncio.to_thread() to avoid blocking the event loop.

Embedding dimension is fixed at 1024 to match the Postgres/pgvector backend
(BGE-M3 output).  Passing a vector of a different dimension raises ValueError.

Metadata filter support is intentionally limited: the vec0 virtual table does
not natively support arbitrary predicate pushdown.  Filtering is applied in
Python after the KNN scan (post-filter), which may return fewer than k results
when the filter is restrictive.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from context_hub.adapters.sqlite.session import open_connection
from context_hub.core.vectorstore import HealthState, HealthStatus, MetaFilter, ScoredId

# sqlite-vec stores vectors as binary blobs; this is the expected dimension.
_EMBEDDING_DIM: int = 1024

# Metadata is stored as JSON in a companion table (see _ensure_meta_table).
_META_TABLE: str = "vec_store_meta"

# Maximum k to prevent DoS via unbounded KNN scans.
_MAX_K: int = 1000


class SqliteVecStore:
    """VectorStore Protocol implementation backed by SQLite + sqlite-vec.

    Args:
        db_path: Path to the SQLite database file. Use ":memory:" for tests.

    Example::

        store = SqliteVecStore(db_path="context_hub.db")
        await store.upsert("doc-1", embedding, {"project_id": "proj-abc"})
        results = await store.knn(query_vec, k=5)
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path: str = str(db_path)

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    async def upsert(
        self,
        doc_id: str,
        embedding: np.ndarray,
        meta: dict[str, Any],
    ) -> None:
        """Insert or replace a single embedding and its metadata.

        Args:
            doc_id:    Stable document identifier (UUID string).
            embedding: Dense float32 vector of shape [1024].
            meta:      Arbitrary JSON-serialisable metadata dict.

        Raises:
            ValueError: If embedding dimension != 1024.
        """
        _validate_embedding(embedding)
        blob = _to_blob(embedding)
        meta_json = json.dumps(meta)
        await asyncio.to_thread(self._sync_upsert, doc_id, blob, meta_json)

    async def knn(
        self,
        query: np.ndarray,
        k: int,
        filter: MetaFilter | None = None,
    ) -> list[ScoredId]:
        """Return the k approximate nearest neighbours for *query*.

        Metadata filters are applied as a post-scan Python filter on the
        retrieved candidates.  Up to k * 10 candidates are fetched to
        accommodate filtering while keeping recall high.

        Args:
            query:  Dense float32 query vector of shape [1024].
            k:      Maximum number of results to return.
            filter: Optional equality filter on metadata fields.

        Returns:
            List of ScoredId sorted by descending cosine similarity, length <= k.

        Raises:
            ValueError: If query dimension != 1024.
        """
        _validate_embedding(query)
        blob = _to_blob(query)
        capped_k = min(k, _MAX_K)
        # Over-fetch to allow post-filtering; cap at a reasonable ceiling.
        fetch_k = capped_k * 10 if filter else capped_k
        raw_rows = await asyncio.to_thread(self._sync_knn, blob, fetch_k)
        return _apply_filter_and_score(raw_rows, filter, capped_k)

    async def delete(self, doc_id: str) -> None:
        """Remove a document from the vector index.

        No-op if *doc_id* does not exist.

        Args:
            doc_id: Document identifier to remove.
        """
        await asyncio.to_thread(self._sync_delete, doc_id)

    async def health_check(self) -> HealthStatus:
        """Verify the vec0 virtual table is accessible.

        Returns:
            HealthStatus with state OK or UNAVAILABLE.
        """
        try:
            await asyncio.to_thread(self._sync_health_check)
            return HealthStatus(state=HealthState.OK)
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(
                state=HealthState.UNAVAILABLE,
                detail=f"sqlite-vec health check failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Synchronous helpers (executed in thread pool)
    # ------------------------------------------------------------------

    def _sync_upsert(self, doc_id: str, blob: bytes, meta_json: str) -> None:
        with open_connection(self._db_path) as conn:
            _ensure_meta_table(conn)
            # vec0 supports DELETE + INSERT for upsert semantics.
            conn.execute(
                "DELETE FROM document_embeddings WHERE doc_id = ?", (doc_id,)
            )
            conn.execute(
                "INSERT INTO document_embeddings (doc_id, embedding) VALUES (?, ?)",
                (doc_id, blob),
            )
            conn.execute(
                f"INSERT OR REPLACE INTO {_META_TABLE} (doc_id, meta_json) "  # noqa: S608
                "VALUES (?, ?)",
                (doc_id, meta_json),
            )
            conn.commit()

    def _sync_knn(
        self, query_blob: bytes, fetch_k: int
    ) -> list[tuple[str, str, float]]:
        """Execute KNN query.  Returns list of (doc_id, meta_json, distance) triples."""
        with open_connection(self._db_path) as conn:
            _ensure_meta_table(conn)
            rows = conn.execute(
                "SELECT e.doc_id, m.meta_json, e.distance "
                "FROM document_embeddings e "
                f"LEFT JOIN {_META_TABLE} m ON e.doc_id = m.doc_id "  # noqa: S608
                "WHERE e.embedding MATCH ? "
                "  AND k = ? "
                "ORDER BY e.distance",
                (query_blob, fetch_k),
            ).fetchall()
            return [(row[0], row[1] or "{}", float(row[2])) for row in rows]

    def _sync_delete(self, doc_id: str) -> None:
        with open_connection(self._db_path) as conn:
            _ensure_meta_table(conn)
            conn.execute(
                "DELETE FROM document_embeddings WHERE doc_id = ?", (doc_id,)
            )
            conn.execute(
                f"DELETE FROM {_META_TABLE} WHERE doc_id = ?",  # noqa: S608
                (doc_id,),
            )
            conn.commit()

    def _sync_health_check(self) -> None:
        with open_connection(self._db_path) as conn:
            conn.execute("SELECT COUNT(*) FROM document_embeddings").fetchone()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_embedding(embedding: np.ndarray) -> None:
    """Raise ValueError if *embedding* is not a 1-D array of length 1024."""
    if embedding.ndim != 1:
        raise ValueError(
            f"Embedding must be 1-D, got shape {embedding.shape}"
        )
    if len(embedding) != _EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension must be {_EMBEDDING_DIM}, got {len(embedding)}"
        )


def _to_blob(embedding: np.ndarray) -> bytes:
    """Serialize a float32 ndarray to a little-endian binary blob for sqlite-vec."""
    return embedding.astype(np.float32).tobytes()


def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    """Create the metadata companion table if it does not exist."""
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_META_TABLE} ("  # noqa: S608
        "    doc_id   TEXT PRIMARY KEY, "
        "    meta_json TEXT NOT NULL DEFAULT '{}'"
        ")"
    )


def _apply_filter_and_score(
    rows: list[tuple[str, str, float]],
    filter: MetaFilter | None,
    k: int,
) -> list[ScoredId]:
    """Apply metadata filter and convert distance to similarity scores.

    sqlite-vec returns L2 distance for cosine-normalised vectors.  We convert
    to cosine similarity via: sim = 1 - (distance^2 / 2), clamped to [0, 1].
    This is exact when both vectors are unit-norm.

    Args:
        rows:   Triples of (doc_id, meta_json, l2_distance) from the KNN scan.
        filter: Optional equality filter; only docs matching ALL keys pass.
        k:      Maximum number of results to return.

    Returns:
        List of ScoredId sorted by descending score, length <= k.
    """
    results: list[ScoredId] = []
    for doc_id, meta_json, distance in rows:
        if filter:
            try:
                meta = json.loads(meta_json)
            except json.JSONDecodeError:
                meta = {}
            if not all(meta.get(key) == val for key, val in filter.items()):
                continue
        # Convert L2 distance to cosine similarity (valid for unit-norm vectors).
        # cosine_sim = 1 - (L2_dist^2 / 2), clamped to [0, 1].
        score = max(0.0, min(1.0, 1.0 - (distance * distance) / 2.0))
        results.append(ScoredId(doc_id=doc_id, score=score))
        if len(results) >= k:
            break
    return results
