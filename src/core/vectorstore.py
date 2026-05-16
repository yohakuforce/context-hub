"""VectorStore Protocol — backend-agnostic vector index abstraction.

Any storage backend (pgvector, sqlite-vec, DuckDB-VSS, …) that satisfies
this Protocol can be used by the search layer without code changes.

Design notes:
- Uses typing.Protocol (structural subtyping) so implementations do NOT need
  to inherit from this class — they just need to expose the same method
  signatures.
- All methods are async to keep the interface uniform across both I/O-bound
  (network DB) and compute-bound (local SQLite) backends.
- MetaFilter is a plain dict so it stays backend agnostic; each adapter is
  responsible for translating it to its native query language.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

import numpy as np


# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


class HealthState(str, Enum):
    """Possible health states returned by VectorStore.health_check()."""

    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class HealthStatus:
    """Immutable health snapshot for a VectorStore backend."""

    state: HealthState
    detail: str = ""


@dataclass(frozen=True)
class ScoredId:
    """A document identifier paired with its relevance score.

    score semantics depend on the retrieval method:
    - Vector search: cosine similarity in [0, 1]
    - Full-text search: BM25 or ts_rank (non-negative, higher = better)
    - RRF fusion: reciprocal rank score (0 < score <= 1/k)
    """

    doc_id: str
    score: float


# MetaFilter is an open-ended dict.  Adapters parse it as needed.
MetaFilter = dict[str, object]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class VectorStore(Protocol):
    """Structural interface for vector index backends.

    Implementors must expose these four async methods.  The Protocol is
    @runtime_checkable so ``isinstance(obj, VectorStore)`` works in tests.
    """

    async def upsert(
        self,
        doc_id: str,
        embedding: np.ndarray,
        meta: dict,
    ) -> None:
        """Insert or update a single embedding with associated metadata.

        Args:
            doc_id:    Stable document identifier (UUID string).
            embedding: Dense float32 vector (shape: [dimensions]).
            meta:      Arbitrary metadata stored alongside the vector.
                       Must be JSON-serialisable.
        """
        ...

    async def knn(
        self,
        query: np.ndarray,
        k: int,
        filter: MetaFilter | None = None,
    ) -> list[ScoredId]:
        """Return the k nearest neighbours for *query*.

        Args:
            query:  Dense float32 query vector.
            k:      Number of results to return.
            filter: Optional metadata filter; only documents matching ALL
                    key-value pairs are considered.

        Returns:
            List of ScoredId sorted by descending score, length <= k.
        """
        ...

    async def delete(self, doc_id: str) -> None:
        """Remove a document from the index.

        No-op if *doc_id* does not exist.
        """
        ...

    async def health_check(self) -> HealthStatus:
        """Return a snapshot of the backend's health."""
        ...
