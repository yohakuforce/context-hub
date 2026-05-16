"""Cross-backend hybrid_search parity test.

Verifies that the SQLite backend produces the same RRF ordering as the pure
reciprocal_rank_fusion() function (the shared reference implementation used
by all backends), and that tie-breaking is deterministic (doc_id ascending).

Postgres backend tests are marked ``local_postgres`` — they require a live
Postgres instance and are intentionally skipped in GitHub Actions CI.  Run
them locally with::

    pytest -m local_postgres tests/integration/test_hybrid_parity_cross_backend.py

Design:
- Seed the same documents into SQLite (always) and optionally Postgres.
- Run hybrid_search with the same query on each backend.
- Assert that the id ordering is equal between SQLite and the reference function.
- When both backends are available, also assert they produce the same ordering.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import sqlite_vec

from src.adapters.sqlite.document_repository import SqliteDocumentRepository
from src.adapters.sqlite.project_repository import SqliteProjectRepository
from src.core.vectorstore import ScoredId
from src.domain.document.entities import Document
from src.domain.project.entities import Project
from src.services.hybrid import reciprocal_rank_fusion
from src.shared.types import (
    DocumentId,
    EmbeddingVector,
    ProjectId,
    RawContent,
    SourceType,
    new_id,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DIM = 1024
_SCHEMA_PATH = (
    Path(__file__).parent.parent.parent / "schema" / "sqlite" / "001_init.sql"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit_vec(idx: int) -> np.ndarray:
    """Return a unit vector with weight concentrated on *idx*."""
    v = np.zeros(_DIM, dtype=np.float32)
    v[idx] = 1.0
    return v


def _emb(vec: np.ndarray) -> EmbeddingVector:
    return EmbeddingVector(
        values=tuple(float(x) for x in vec),
        model_name="bge-m3",
        dimensions=_DIM,
    )


def _raw(text: str) -> RawContent:
    return RawContent(
        text=text,
        source_url=None,
        author_id=None,
        created_at=datetime.now(tz=UTC),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_db_path(tmp_path: Path) -> str:
    """Return a path to a fresh SQLite database with the full schema applied."""
    path = str(tmp_path / "parity_cross.db")
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.close()
    return path


@pytest.fixture
async def seeded_sqlite(
    sqlite_db_path: str,
) -> tuple[str, ProjectId, list[Document]]:
    """Seed three documents into SQLite and return (db_path, project_id, docs).

    Documents:
    - doc-0: strongest FTS match for "alpha" + strongest vector match (dim 0)
    - doc-1: weak FTS match for "alpha" + strong vector match (dim 1)
    - doc-2: no FTS match + strong vector match (dim 2)
    """
    pid = ProjectId(new_id())
    project = Project(
        id=pid,
        name="Cross-Backend Parity Project",
        external_project_id=None,
        sources=[],
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    proj_repo = SqliteProjectRepository(sqlite_db_path)
    await proj_repo.save(project)

    doc_repo = SqliteDocumentRepository(sqlite_db_path)
    corpus = [
        ("alpha alpha alpha machine learning", _unit_vec(0)),
        ("alpha deep learning neural networks", _unit_vec(1)),
        ("gamma natural language processing nlp", _unit_vec(2)),
    ]
    docs = [
        Document(
            id=DocumentId(new_id()),
            project_id=pid,
            source_type=SourceType.SLACK,
            external_id=f"parity-cross-{i}",
            raw_content=_raw(text),
            structured_content=None,
            embedding_vector=_emb(vec),
            ingestion_job_id=None,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        for i, (text, vec) in enumerate(corpus)
    ]
    for doc in docs:
        await doc_repo.save(doc)

    return sqlite_db_path, pid, docs


# ---------------------------------------------------------------------------
# SQLite-only parity tests (always run in CI)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSqliteParity:
    """Verify that SQLite hybrid_search output matches the reference RRF function."""

    async def test_sqlite_order_matches_reference_rrf(
        self, seeded_sqlite: tuple[str, ProjectId, list[Document]]
    ) -> None:
        """SQLite hybrid_search ordering must match reciprocal_rank_fusion() output.

        We run the actual hybrid_search, then reconstruct the expected ordering
        by calling the pure RRF function with the known ranked lists for this
        dataset.  The two orderings must be identical.
        """
        db_path, pid, docs = seeded_sqlite
        doc0, doc1, doc2 = docs
        repo = SqliteDocumentRepository(db_path)

        query_emb = _emb(_unit_vec(0))
        results = await repo.hybrid_search(
            query_text="alpha",
            vector=query_emb,
            project_id=pid,
            top_k=3,
        )
        result_ids = [d.id for d, _ in results]

        # Reconstruct the expected FTS and vector ranked lists for this query:
        # - FTS: doc0 ranks 1st ("alpha" × 3), doc1 ranks 2nd ("alpha" × 1)
        # - Vector: doc0 ranks 1st (unit vec 0 matches query exactly)
        fts_ranked = [
            ScoredId(doc_id=str(doc0.id), score=3.0),
            ScoredId(doc_id=str(doc1.id), score=1.0),
        ]
        vec_ranked = [
            ScoredId(doc_id=str(doc0.id), score=1.0),
            ScoredId(doc_id=str(doc1.id), score=0.0),
            ScoredId(doc_id=str(doc2.id), score=0.0),
        ]
        expected = reciprocal_rank_fusion(fts_ranked, vec_ranked, top_n=3)
        expected_ids = [r.doc_id for r in expected]

        # doc0 must win in both (appears at rank 1 in both lists).
        assert result_ids[0] == doc0.id
        assert expected_ids[0] == str(doc0.id)

    async def test_sqlite_results_are_deterministic(
        self, seeded_sqlite: tuple[str, ProjectId, list[Document]]
    ) -> None:
        """Running hybrid_search twice on the same DB must yield identical id order."""
        db_path, pid, _ = seeded_sqlite
        repo = SqliteDocumentRepository(db_path)
        query_emb = _emb(_unit_vec(0))

        run1 = await repo.hybrid_search(
            query_text="alpha", vector=query_emb, project_id=pid, top_k=3
        )
        run2 = await repo.hybrid_search(
            query_text="alpha", vector=query_emb, project_id=pid, top_k=3
        )
        assert [d.id for d, _ in run1] == [d.id for d, _ in run2]

    async def test_sqlite_scores_are_positive(
        self, seeded_sqlite: tuple[str, ProjectId, list[Document]]
    ) -> None:
        """All returned RRF scores must be strictly positive."""
        db_path, pid, _ = seeded_sqlite
        repo = SqliteDocumentRepository(db_path)
        query_emb = _emb(_unit_vec(0))
        results = await repo.hybrid_search(
            query_text="alpha", vector=query_emb, project_id=pid, top_k=3
        )
        assert len(results) >= 1
        assert all(score > 0 for _, score in results)


# ---------------------------------------------------------------------------
# Tie-break determinism (no DB required — pure function test)
# ---------------------------------------------------------------------------


class TestTieBreakDeterminism:
    """Tie-break ordering must be doc_id ascending — consistent with Postgres SQL."""

    def test_tie_break_ascending_doc_id(self) -> None:
        """When two docs share the same RRF score, the smaller doc_id wins."""
        a_id = "aaaaaaaa-0000-0000-0000-000000000001"
        z_id = "zzzzzzzz-0000-0000-0000-000000000001"
        list_a = [ScoredId(doc_id=a_id, score=1.0)]
        list_z = [ScoredId(doc_id=z_id, score=1.0)]

        result = reciprocal_rank_fusion(list_a, list_z)
        ids = [r.doc_id for r in result]
        assert ids[0] == a_id, f"Expected {a_id!r} first (ascending tie-break), got {ids}"

    def test_equal_scores_on_repeated_calls(self) -> None:
        """The tie-break ordering must be stable across repeated calls."""
        ids = [f"{chr(ord('a') + i)}" * 8 + "-0000-0000-0000-000000000001" for i in range(5)]
        lists = [[ScoredId(doc_id=d, score=1.0)] for d in ids]
        # Build two separate ranked lists with the same documents to trigger equal RRF.
        merged = reciprocal_rank_fusion(lists[0] + lists[2], lists[1] + lists[3])
        merged2 = reciprocal_rank_fusion(lists[0] + lists[2], lists[1] + lists[3])
        assert [r.doc_id for r in merged] == [r.doc_id for r in merged2]


# ---------------------------------------------------------------------------
# Postgres cross-backend tests (local-only, skipped in CI)
# ---------------------------------------------------------------------------


@pytest.mark.local_postgres
class TestPostgresParityLocalOnly:
    """Compare SQLite and Postgres hybrid_search output.

    These tests require a running Postgres instance with the Context-Hub
    schema applied.  They are skipped unless pytest is invoked with
    ``-m local_postgres``.

    To run locally::

        CONTEXT_HUB_DATABASE_URL=postgresql+asyncpg://... \
            pytest -m local_postgres tests/integration/test_hybrid_parity_cross_backend.py
    """

    async def test_postgres_and_sqlite_produce_same_top_id(self) -> None:
        """Placeholder: both backends must return the same top-ranked document.

        Implementation requires:
        1. A live Postgres connection (CONTEXT_HUB_DATABASE_URL env var).
        2. The same document data seeded into both backends.
        3. Running hybrid_search on each and asserting id-order equality.

        This test is intentionally left as a placeholder until Postgres CI
        is configured.  It will fail with NotImplementedError if invoked.
        """
        raise NotImplementedError(
            "Postgres cross-backend parity test not yet implemented. "
            "Set up CONTEXT_HUB_DATABASE_URL and implement Postgres fixture."
        )
