"""Windows / no-sqlite-vec fallback: degraded FTS-only mode must still work.

On the official python.org Windows builds, `sqlite3` is compiled without
loadable-extension support, so sqlite-vec cannot load. Context-Hub must then
run in **degraded FTS-only mode**: `migrate` succeeds (skipping the vec0 table),
ingestion works, and keyword (FTS5) search still returns results — only semantic
vector search is disabled.

These tests reproduce that environment on any platform by forcing the cached
`vec_extension_available()` probe to False, then exercising the real
SqliteMigrationRunner + SqliteDocumentRepository code paths.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from context_hub.adapters.sqlite import session as sqlite_session
from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
from context_hub.adapters.sqlite.migration_runner import SqliteMigrationRunner
from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
from context_hub.domain.document.entities import Document
from context_hub.domain.project.entities import Project
from context_hub.shared.types import (
    DocumentId,
    EmbeddingVector,
    ProjectId,
    RawContent,
    SourceType,
    new_id,
)

_DIM = 1024


@pytest.fixture
def degraded_mode() -> Iterator[None]:
    """Force sqlite-vec to appear unavailable for the duration of the test."""
    original = sqlite_session._vec_available
    sqlite_session._vec_available = False
    try:
        yield
    finally:
        sqlite_session._vec_available = original


def _table_names(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def _make_document(project_id: ProjectId, external_id: str, text: str) -> Document:
    return Document(
        id=DocumentId(new_id()),
        project_id=project_id,
        source_type=SourceType.MEETING,
        external_id=external_id,
        raw_content=RawContent(
            text=text, source_url=None, author_id=None, created_at=datetime.utcnow()
        ),
        structured_content=None,
        # Embedding is present but must be silently ignored in degraded mode.
        embedding_vector=EmbeddingVector(
            values=tuple(0.0 for _ in range(_DIM)),
            model_name="bge-m3",
            dimensions=_DIM,
        ),
        ingestion_job_id=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_migrate_succeeds_and_skips_vec0_table(
    degraded_mode: None, tmp_path: Path
) -> None:
    """migrate must succeed without sqlite-vec, creating FTS but not vec0 tables."""
    db_path = str(tmp_path / "degraded.db")

    await SqliteMigrationRunner(db_path=db_path).upgrade()

    tables = _table_names(db_path)
    assert "documents" in tables
    assert "document_fts" in tables  # FTS5 keyword index still created
    assert "document_embeddings" not in tables  # vec0 table skipped


@pytest.mark.asyncio
async def test_ingest_and_keyword_search_work_without_vec(
    degraded_mode: None, tmp_path: Path
) -> None:
    """A document can be saved and found via keyword (FTS) search in degraded mode."""
    db_path = str(tmp_path / "degraded.db")
    await SqliteMigrationRunner(db_path=db_path).upgrade()

    pid = ProjectId(new_id())
    await SqliteProjectRepository(db_path).save(
        Project(
            id=pid,
            name="Degraded",
            external_project_id=None,
            sources=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )

    repo = SqliteDocumentRepository(db_path)
    # Saving with an embedding present must NOT crash (embedding insert skipped).
    await repo.save(
        _make_document(pid, "m-1", "The kickoff meeting decided to ship bundle plan A")
    )

    # Keyword (FTS5) search still returns the document; vector arm is empty.
    zero_vec = EmbeddingVector(
        values=tuple(0.0 for _ in range(_DIM)), model_name="bge-m3", dimensions=_DIM
    )
    results = await repo.hybrid_search(
        query_text="bundle plan",
        vector=zero_vec,
        project_id=pid,
        top_k=5,
    )

    assert len(results) >= 1
    assert any("bundle plan A" in doc.raw_content.text for doc, _ in results)


def test_vec_extension_available_is_cached() -> None:
    """The probe result is cached after the first call (no repeated probing)."""
    # Reset cache, then probe twice — second call must use the cached value.
    original = sqlite_session._vec_available
    try:
        sqlite_session._vec_available = None
        first = sqlite_session.vec_extension_available()
        assert sqlite_session._vec_available is first
        second = sqlite_session.vec_extension_available()
        assert first is second
    finally:
        sqlite_session._vec_available = original
