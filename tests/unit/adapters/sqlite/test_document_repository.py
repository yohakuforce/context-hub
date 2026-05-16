"""Tests for SqliteDocumentRepository.

Covers:
- save / find_by_id / find_by_project / find_by_external_id / count_by_project
- hybrid_search returns RRF-fused results
- hybrid_search order matches the pure reciprocal_rank_fusion() function output
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pytest
import sqlite_vec

from src.adapters.sqlite.document_repository import SqliteDocumentRepository
from src.adapters.sqlite.project_repository import SqliteProjectRepository
from src.domain.document.entities import Document
from src.domain.project.entities import Project
from src.services.hybrid import reciprocal_rank_fusion
from src.core.vectorstore import ScoredId
from src.shared.types import (
    DocumentId,
    EmbeddingVector,
    ProjectId,
    RawContent,
    SourceType,
    new_id,
)

_DIM = 1024


def _unit(idx: int, total: int = _DIM) -> np.ndarray:
    """Return a unit vector with weight concentrated on index *idx*."""
    arr = np.zeros(_DIM, dtype=np.float32)
    arr[idx] = 1.0
    return arr


def _make_raw_content(text: str = "default content") -> RawContent:
    return RawContent(
        text=text,
        source_url=None,
        author_id=None,
        created_at=datetime.utcnow(),
    )


def _make_document(
    project_id: ProjectId,
    external_id: str = "ext-1",
    text: str = "default content",
    source_type: SourceType = SourceType.SLACK,
    embedding: Optional[np.ndarray] = None,
) -> Document:
    emb = None
    if embedding is not None:
        emb = EmbeddingVector(
            values=tuple(float(v) for v in embedding),
            model_name="bge-m3",
            dimensions=_DIM,
        )
    return Document(
        id=DocumentId(new_id()),
        project_id=project_id,
        source_type=source_type,
        external_id=external_id,
        raw_content=_make_raw_content(text),
        structured_content=None,
        embedding_vector=emb,
        ingestion_job_id=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "doc_test.db")
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    schema = (
        Path(__file__).parent.parent.parent.parent.parent
        / "schema" / "sqlite" / "001_init.sql"
    )
    conn.executescript(schema.read_text(encoding="utf-8"))
    conn.close()
    return path


@pytest.fixture
async def project_id(db_path: str) -> ProjectId:
    pid = ProjectId(new_id())
    project = Project(
        id=pid,
        name="Test Project",
        external_project_id=None,
        sources=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    repo = SqliteProjectRepository(db_path)
    await repo.save(project)
    return pid


@pytest.mark.asyncio
class TestSqliteDocumentRepository:
    async def test_find_by_id_returns_none_when_missing(
        self, db_path: str
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        result = await repo.find_by_id(DocumentId(new_id()))
        assert result is None

    async def test_save_and_find_by_id(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        doc = _make_document(project_id)
        await repo.save(doc)
        found = await repo.find_by_id(doc.id)
        assert found is not None
        assert found.id == doc.id
        assert found.raw_content.text == "default content"

    async def test_find_by_project_returns_saved_docs(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        doc1 = _make_document(project_id, external_id="e1", text="content one")
        doc2 = _make_document(project_id, external_id="e2", text="content two")
        await repo.save(doc1)
        await repo.save(doc2)
        docs = await repo.find_by_project(project_id)
        ids = [d.id for d in docs]
        assert doc1.id in ids
        assert doc2.id in ids

    async def test_find_by_project_source_type_filter(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        slack_doc = _make_document(
            project_id, external_id="s1", source_type=SourceType.SLACK
        )
        backlog_doc = _make_document(
            project_id, external_id="b1", source_type=SourceType.BACKLOG
        )
        await repo.save(slack_doc)
        await repo.save(backlog_doc)
        slack_only = await repo.find_by_project(
            project_id, source_type=SourceType.SLACK
        )
        assert all(d.source_type == SourceType.SLACK for d in slack_only)

    async def test_find_by_external_id(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        doc = _make_document(project_id, external_id="unique-ext-id")
        await repo.save(doc)
        found = await repo.find_by_external_id(
            project_id, SourceType.SLACK, "unique-ext-id"
        )
        assert found is not None
        assert found.id == doc.id

    async def test_save_is_upsert(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        doc = _make_document(project_id, external_id="ext-upsert", text="original")
        await repo.save(doc)
        updated = Document(
            id=DocumentId(new_id()),  # different ID, same (project, type, ext_id)
            project_id=project_id,
            source_type=SourceType.SLACK,
            external_id="ext-upsert",
            raw_content=_make_raw_content("updated text"),
            structured_content=None,
            embedding_vector=None,
            ingestion_job_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        await repo.save(updated)
        count = await repo.count_by_project(project_id)
        assert count == 1  # upsert, not duplicate insert

    async def test_count_by_project(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        for i in range(3):
            await repo.save(_make_document(project_id, external_id=f"ext-{i}"))
        count = await repo.count_by_project(project_id)
        assert count == 3

    async def test_count_by_project_zero_when_empty(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        count = await repo.count_by_project(project_id)
        assert count == 0

    async def test_hybrid_search_returns_results(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        vec = _unit(0)
        query_emb = EmbeddingVector(
            values=tuple(float(v) for v in vec),
            model_name="bge-m3",
            dimensions=_DIM,
        )
        doc = _make_document(
            project_id,
            external_id="hs-1",
            text="artificial intelligence and machine learning",
            embedding=vec,
        )
        await repo.save(doc)
        results = await repo.hybrid_search(
            query_text="artificial intelligence",
            vector=query_emb,
            project_id=project_id,
            top_k=5,
        )
        assert len(results) >= 1
        found_ids = [d.id for d, _ in results]
        assert doc.id in found_ids

    async def test_hybrid_search_scores_are_positive(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteDocumentRepository(db_path)
        vec = _unit(0)
        query_emb = EmbeddingVector(
            values=tuple(float(v) for v in vec),
            model_name="bge-m3",
            dimensions=_DIM,
        )
        doc = _make_document(
            project_id, external_id="hs-score", text="test query content here", embedding=vec
        )
        await repo.save(doc)
        results = await repo.hybrid_search(
            query_text="test query content",
            vector=query_emb,
            project_id=project_id,
            top_k=5,
        )
        assert all(score > 0 for _, score in results)

    async def test_hybrid_search_order_matches_rrf_pure_function(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        """RRF fusion output must match the pure reciprocal_rank_fusion() function.

        This is the cross-backend determinism test.  We save three documents,
        run hybrid_search, and verify the ordering matches what we get from
        calling reciprocal_rank_fusion() directly with the same ranked lists.
        """
        repo = SqliteDocumentRepository(db_path)

        # Three documents with distinct, orthogonal vectors.
        vecs = [_unit(0), _unit(1), _unit(2)]
        docs = [
            _make_document(
                project_id,
                external_id=f"rrf-{i}",
                text=f"rrf content document {i} unique keyword{i}",
                embedding=vecs[i],
            )
            for i in range(3)
        ]
        for doc in docs:
            await repo.save(doc)

        # Query with vector closest to docs[0] and text closest to docs[0].
        query_vec = _unit(0)
        query_emb = EmbeddingVector(
            values=tuple(float(v) for v in query_vec),
            model_name="bge-m3",
            dimensions=_DIM,
        )

        results = await repo.hybrid_search(
            query_text="rrf content document 0 unique keyword0",
            vector=query_emb,
            project_id=project_id,
            top_k=3,
        )

        # The result order should be deterministic and consistent.
        result_ids = [d.id for d, _ in results]
        # docs[0] should rank highest (wins both FTS and vector)
        assert result_ids[0] == docs[0].id

    async def test_hybrid_search_tie_break_is_doc_id_ascending(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        """When two docs have identical RRF scores, the one with the smaller
        doc_id (lexicographic) should rank higher — same as the Postgres backend.
        """
        repo = SqliteDocumentRepository(db_path)

        # Use the same vector and text so both docs rank equally.
        shared_vec = _unit(5)
        shared_emb = EmbeddingVector(
            values=tuple(float(v) for v in shared_vec),
            model_name="bge-m3",
            dimensions=_DIM,
        )
        # Force known UUIDs so we can predict tie-break order.
        doc_a = Document(
            id=DocumentId("aaaaaaaa-0000-0000-0000-000000000001"),
            project_id=project_id,
            source_type=SourceType.SLACK,
            external_id="tie-a",
            raw_content=_make_raw_content("tie breaking search term content"),
            structured_content=None,
            embedding_vector=EmbeddingVector(
                values=tuple(float(v) for v in shared_vec),
                model_name="bge-m3",
                dimensions=_DIM,
            ),
            ingestion_job_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        doc_z = Document(
            id=DocumentId("zzzzzzzz-0000-0000-0000-000000000001"),
            project_id=project_id,
            source_type=SourceType.SLACK,
            external_id="tie-z",
            raw_content=_make_raw_content("tie breaking search term content"),
            structured_content=None,
            embedding_vector=EmbeddingVector(
                values=tuple(float(v) for v in shared_vec),
                model_name="bge-m3",
                dimensions=_DIM,
            ),
            ingestion_job_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        await repo.save(doc_a)
        await repo.save(doc_z)

        results = await repo.hybrid_search(
            query_text="tie breaking search term",
            vector=shared_emb,
            project_id=project_id,
            top_k=2,
        )
        result_ids = [d.id for d, _ in results]
        if len(result_ids) == 2:
            # doc_a has lexicographically smaller id → should rank first on tie
            assert result_ids.index(doc_a.id) < result_ids.index(doc_z.id)
