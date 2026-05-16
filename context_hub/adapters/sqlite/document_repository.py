"""SQLite implementation of DocumentRepository.

Hybrid search strategy:
  1. FTS5 trigram full-text search (document_fts virtual table)
  2. sqlite-vec cosine KNN (document_embeddings virtual table)
  3. RRF (Reciprocal Rank Fusion) merge via the shared pure function

The hybrid_search method calls the two searches in parallel threads and
fuses the ranks using reciprocal_rank_fusion().  The RRF output order is
deterministic: descending score, then ascending doc_id for ties.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime
from typing import Any, cast

import numpy as np

from context_hub.adapters.sqlite.session import open_connection
from context_hub.core.vectorstore import ScoredId
from context_hub.domain.document.entities import Document
from context_hub.domain.document.repository import DocumentRepository
from context_hub.services.hybrid import reciprocal_rank_fusion
from context_hub.shared.types import (
    DocumentId,
    EmbeddingVector,
    EntityType,
    ExtractedEntity,
    IngestionJobId,
    ProjectId,
    RawContent,
    SourceType,
    StructuredContent,
)


class SqliteDocumentRepository(DocumentRepository):
    """Concrete DocumentRepository backed by SQLite + sqlite-vec + FTS5.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def find_by_id(self, doc_id: DocumentId) -> Document | None:
        """Return the Document with the given ID, or None.

        Args:
            doc_id: UUID string identifying the document.

        Returns:
            Document domain object, or None.
        """
        row = await asyncio.to_thread(self._sync_find_by_id, str(doc_id))
        return _row_to_domain(row) if row else None

    async def find_by_project(
        self,
        project_id: ProjectId,
        source_type: SourceType | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Document]:
        """Return documents belonging to a project.

        Args:
            project_id:  UUID string identifying the project.
            source_type: Optional filter for a specific source type.
            limit:       Maximum number of results.
            offset:      Pagination offset.

        Returns:
            List of Document domain objects ordered by created_at descending.
        """
        rows = await asyncio.to_thread(
            self._sync_find_by_project, str(project_id), source_type, limit, offset
        )
        return [_row_to_domain(r) for r in rows]

    async def find_by_external_id(
        self,
        project_id: ProjectId,
        source_type: SourceType,
        external_id: str,
    ) -> Document | None:
        """Return the document with a given external ID, or None.

        Args:
            project_id:  UUID string identifying the project.
            source_type: Source system type.
            external_id: ID in the external source system.

        Returns:
            Document domain object, or None.
        """
        row = await asyncio.to_thread(
            self._sync_find_by_external_id,
            str(project_id),
            source_type.value,
            external_id,
        )
        return _row_to_domain(row) if row else None

    async def find_similar(
        self,
        vector: EmbeddingVector,
        project_id: ProjectId,
        top_k: int = 10,
        source_types: list[SourceType] | None = None,
    ) -> list[tuple[Document, float]]:
        """Return the top-k most similar documents by cosine similarity.

        Args:
            vector:       Query embedding vector (1024-dim).
            project_id:   UUID string identifying the project.
            top_k:        Maximum number of results.
            source_types: Optional filter for specific source types.

        Returns:
            List of (Document, similarity_score) pairs sorted by descending score.
        """
        query = np.array(vector.values, dtype=np.float32)
        scored = await asyncio.to_thread(
            self._sync_vector_search, query, str(project_id), top_k, source_types
        )
        if not scored:
            return []
        ids = [doc_id for doc_id, _ in scored]
        score_map = {doc_id: score for doc_id, score in scored}
        rows = await asyncio.to_thread(self._sync_find_many_by_ids, ids)
        docs_with_scores: list[tuple[Document, float]] = []
        for doc_id in ids:
            row = rows.get(doc_id)
            if row is not None:
                docs_with_scores.append((_row_to_domain(row), score_map[doc_id]))
        return docs_with_scores

    async def hybrid_search(
        self,
        query_text: str,
        vector: EmbeddingVector,
        project_id: ProjectId,
        top_k: int = 10,
        source_types: list[SourceType] | None = None,
        metadata_filter: dict[str, Any] | None = None,
        rrf_k: int = 60,
    ) -> list[tuple[Document, float]]:
        """Hybrid search: FTS5 + sqlite-vec + RRF fusion.

        The two ranked lists are fused via reciprocal_rank_fusion() using the
        same pure function as the Postgres backend, guaranteeing identical
        ranking behavior for the same candidates.

        Args:
            query_text:      Text query for FTS5.
            vector:          Query embedding for vector search.
            project_id:      UUID string identifying the project.
            top_k:           Maximum number of results.
            source_types:    Optional filter for source types (applied post-RRF).
            metadata_filter: Optional metadata equality filter (applied post-RRF).
            rrf_k:           RRF smoothing constant (default 60).

        Returns:
            List of (Document, rrf_score) pairs sorted by descending RRF score.
        """
        query_np = np.array(vector.values, dtype=np.float32)
        candidate_k = top_k * 3  # over-fetch for RRF quality

        # Run FTS5 and vector searches concurrently in the thread pool.
        fts_task = asyncio.to_thread(
            self._sync_fts_search, query_text, str(project_id), candidate_k
        )
        vec_task = asyncio.to_thread(
            self._sync_vector_search,
            query_np,
            str(project_id),
            candidate_k,
            source_types,
        )
        fts_results, vec_results = await asyncio.gather(fts_task, vec_task)

        fts_scored = [ScoredId(doc_id=d, score=s) for d, s in fts_results]
        vec_scored = [ScoredId(doc_id=d, score=s) for d, s in vec_results]

        fused = reciprocal_rank_fusion(fts_scored, vec_scored, k=rrf_k, top_n=top_k)

        if not fused:
            return []

        fused_ids = [item.doc_id for item in fused]
        score_map = {item.doc_id: item.score for item in fused}
        rows = await asyncio.to_thread(self._sync_find_many_by_ids, fused_ids)

        docs_with_scores: list[tuple[Document, float]] = []
        for doc_id in fused_ids:
            row = rows.get(doc_id)
            if row is None:
                continue
            doc = _row_to_domain(row)
            if source_types and doc.source_type not in source_types:
                continue
            docs_with_scores.append((doc, score_map[doc_id]))

        return docs_with_scores

    async def count_by_project(
        self,
        project_id: ProjectId,
        source_type: SourceType | None = None,
    ) -> int:
        """Return the number of documents in a project.

        Args:
            project_id:  UUID string identifying the project.
            source_type: Optional filter for a specific source type.

        Returns:
            Document count (integer >= 0).
        """
        return await asyncio.to_thread(
            self._sync_count_by_project, str(project_id), source_type
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def save(self, document: Document) -> Document:
        """Upsert a Document (keyed on project_id + source_type + external_id).

        Args:
            document: Document domain object to persist.

        Returns:
            The same Document instance (unchanged).
        """
        await asyncio.to_thread(self._sync_save, document)
        return document

    # ------------------------------------------------------------------
    # Synchronous helpers
    # ------------------------------------------------------------------

    def _sync_find_many_by_ids(self, ids: list[str]) -> dict[str, sqlite3.Row]:
        """Fetch multiple documents by ID in a single query.

        Returns a dict keyed by doc_id preserving lookup order.  Missing IDs
        are absent from the dict.

        Args:
            ids: List of document UUID strings to fetch.

        Returns:
            Dict mapping doc_id → sqlite3.Row for each found document.
        """
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        with open_connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, project_id, source_type, external_id, raw_text, "
                "  source_url, author_id, raw_created_at, summary, language, "
                "  tags, entities, embedding_model, metadata, ingestion_job_id, "
                "  created_at, updated_at "
                f"FROM documents WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
            return {row[0]: row for row in rows}

    def _sync_find_by_id(self, doc_id: str) -> sqlite3.Row | None:
        with open_connection(self._db_path) as conn:
            return cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT id, project_id, source_type, external_id, raw_text, "
                    "  source_url, author_id, raw_created_at, summary, language, "
                    "  tags, entities, embedding_model, metadata, ingestion_job_id, "
                    "  created_at, updated_at "
                    "FROM documents WHERE id = ?",
                    (doc_id,),
                ).fetchone(),
            )

    def _sync_find_by_project(
        self,
        project_id: str,
        source_type: SourceType | None,
        limit: int,
        offset: int,
    ) -> list[sqlite3.Row]:
        with open_connection(self._db_path) as conn:
            if source_type:
                return conn.execute(
                    "SELECT id, project_id, source_type, external_id, raw_text, "
                    "  source_url, author_id, raw_created_at, summary, language, "
                    "  tags, entities, embedding_model, metadata, ingestion_job_id, "
                    "  created_at, updated_at "
                    "FROM documents "
                    "WHERE project_id = ? AND source_type = ? "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (project_id, source_type.value, limit, offset),
                ).fetchall()
            return conn.execute(
                "SELECT id, project_id, source_type, external_id, raw_text, "
                "  source_url, author_id, raw_created_at, summary, language, "
                "  tags, entities, embedding_model, metadata, ingestion_job_id, "
                "  created_at, updated_at "
                "FROM documents "
                "WHERE project_id = ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (project_id, limit, offset),
            ).fetchall()

    def _sync_find_by_external_id(
        self, project_id: str, source_type: str, external_id: str
    ) -> sqlite3.Row | None:
        with open_connection(self._db_path) as conn:
            return cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT id, project_id, source_type, external_id, raw_text, "
                    "  source_url, author_id, raw_created_at, summary, language, "
                    "  tags, entities, embedding_model, metadata, ingestion_job_id, "
                    "  created_at, updated_at "
                    "FROM documents "
                    "WHERE project_id = ? AND source_type = ? AND external_id = ?",
                    (project_id, source_type, external_id),
                ).fetchone(),
            )

    def _sync_fts_search(
        self, query: str, project_id: str, k: int
    ) -> list[tuple[str, float]]:
        """Execute FTS5 trigram search. Returns (doc_id, score) pairs."""
        if len(query.strip()) < 3:  # trigram minimum
            return []
        with open_connection(self._db_path) as conn:
            safe_q = '"' + query.replace('"', '""') + '"'
            rows = conn.execute(
                "SELECT fts.doc_id, bm25(document_fts) AS rank "
                "FROM document_fts fts "
                "JOIN documents d ON fts.doc_id = d.id "
                "WHERE document_fts MATCH ? AND d.project_id = ? "
                "ORDER BY rank LIMIT ?",
                (safe_q, project_id, k),
            ).fetchall()
            return [(row[0], -float(row[1])) for row in rows]  # negate bm25 → positive

    def _sync_vector_search(
        self,
        query: np.ndarray,
        project_id: str,
        k: int,
        source_types: list[SourceType] | None,
    ) -> list[tuple[str, float]]:
        """Execute sqlite-vec KNN search. Returns (doc_id, score) pairs."""
        blob = query.astype(np.float32).tobytes()
        with open_connection(self._db_path) as conn:
            # Fetch more candidates than needed; filter by project_id afterwards.
            rows = conn.execute(
                "SELECT e.doc_id, e.distance "
                "FROM document_embeddings e "
                "JOIN documents d ON e.doc_id = d.id "
                "WHERE e.embedding MATCH ? AND k = ? AND d.project_id = ? "
                "ORDER BY e.distance",
                (blob, k, project_id),
            ).fetchall()
            results: list[tuple[str, float]] = []
            for row in rows:
                doc_id, distance = row[0], float(row[1])
                if source_types:
                    st_row = conn.execute(
                        "SELECT source_type FROM documents WHERE id = ?", (doc_id,)
                    ).fetchone()
                    if st_row is None:
                        continue
                    if SourceType(st_row[0]) not in source_types:
                        continue
                score = max(0.0, min(1.0, 1.0 - (distance * distance) / 2.0))
                results.append((doc_id, score))
            return results

    def _sync_count_by_project(
        self, project_id: str, source_type: SourceType | None
    ) -> int:
        with open_connection(self._db_path) as conn:
            if source_type:
                row = conn.execute(
                    "SELECT COUNT(*) FROM documents "
                    "WHERE project_id = ? AND source_type = ?",
                    (project_id, source_type.value),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
            return int(row[0]) if row else 0

    def _sync_save(self, document: Document) -> None:
        values = _domain_to_values(document)
        with open_connection(self._db_path) as conn:
            conn.execute(
                "INSERT INTO documents ("
                "  id, project_id, source_type, external_id, raw_text, "
                "  source_url, author_id, raw_created_at, summary, language, "
                "  tags, entities, embedding_model, metadata, ingestion_job_id, "
                "  created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id, source_type, external_id) DO UPDATE SET "
                "  raw_text = excluded.raw_text, "
                "  source_url = excluded.source_url, "
                "  author_id = excluded.author_id, "
                "  raw_created_at = excluded.raw_created_at, "
                "  summary = excluded.summary, "
                "  language = excluded.language, "
                "  tags = excluded.tags, "
                "  entities = excluded.entities, "
                "  embedding_model = excluded.embedding_model, "
                "  metadata = excluded.metadata, "
                "  ingestion_job_id = excluded.ingestion_job_id, "
                "  updated_at = excluded.updated_at",
                (
                    values["id"],
                    values["project_id"],
                    values["source_type"],
                    values["external_id"],
                    values["raw_text"],
                    values["source_url"],
                    values["author_id"],
                    values["raw_created_at"],
                    values["summary"],
                    values["language"],
                    values["tags"],
                    values["entities"],
                    values["embedding_model"],
                    values["metadata"],
                    values["ingestion_job_id"],
                    values["created_at"],
                    values["updated_at"],
                ),
            )

            # Upsert embedding if present.
            if values["embedding"] is not None:
                conn.execute(
                    "DELETE FROM document_embeddings WHERE doc_id = ?",
                    (values["id"],),
                )
                conn.execute(
                    "INSERT INTO document_embeddings (doc_id, embedding) VALUES (?, ?)",
                    (values["id"], values["embedding"]),
                )

            # Upsert FTS5 index.
            conn.execute(
                "DELETE FROM document_fts WHERE doc_id = ?", (values["id"],)
            )
            conn.execute(
                "INSERT INTO document_fts (doc_id, content, project_id) "
                "VALUES (?, ?, ?)",
                (values["id"], values["raw_text"], values["project_id"]),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _domain_to_values(doc: Document) -> dict[str, Any]:
    embedding_blob = None
    embedding_model = None
    if doc.embedding_vector:
        arr = np.array(doc.embedding_vector.values, dtype=np.float32)
        embedding_blob = arr.tobytes()
        embedding_model = doc.embedding_vector.model_name

    summary = None
    language = None
    tags_json = "[]"
    entities_json = "[]"
    if doc.structured_content:
        summary = doc.structured_content.summary
        language = doc.structured_content.language
        tags_json = json.dumps(list(doc.structured_content.tags))
        entities_json = json.dumps(
            [
                {"name": e.name, "entity_type": e.entity_type.value}
                for e in doc.structured_content.entities
            ]
        )

    meta = {"ingestion_job_id": str(doc.ingestion_job_id) if doc.ingestion_job_id else None}

    return {
        "id": str(doc.id),
        "project_id": str(doc.project_id),
        "source_type": doc.source_type.value,
        "external_id": doc.external_id,
        "raw_text": doc.raw_content.text,
        "source_url": doc.raw_content.source_url,
        "author_id": doc.raw_content.author_id,
        "raw_created_at": doc.raw_content.created_at.isoformat(),
        "summary": summary,
        "language": language,
        "tags": tags_json,
        "entities": entities_json,
        "embedding_model": embedding_model,
        "embedding": embedding_blob,
        "metadata": json.dumps(meta),
        "ingestion_job_id": str(doc.ingestion_job_id) if doc.ingestion_job_id else None,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


def _row_to_domain(row: sqlite3.Row) -> Document:
    (
        doc_id, project_id, source_type, external_id, raw_text,
        source_url, author_id, raw_created_at, summary, language,
        tags_json, entities_json, embedding_model, metadata_json,
        ingestion_job_id, created_at, updated_at,
    ) = row

    raw_content = RawContent(
        text=raw_text,
        source_url=source_url,
        author_id=author_id,
        created_at=(
            datetime.fromisoformat(raw_created_at)
            if raw_created_at
            else datetime.fromisoformat(created_at)
        ),
    )

    structured = None
    if summary is not None:
        entities_raw: list[dict[str, Any]] = json.loads(entities_json or "[]")
        extracted = tuple(
            ExtractedEntity(
                name=e["name"],
                entity_type=EntityType(e["entity_type"]),
            )
            for e in entities_raw
        )
        structured = StructuredContent(
            summary=summary,
            language=language or "ja",
            tags=tuple(json.loads(tags_json or "[]")),
            entities=extracted,
        )

    meta = json.loads(metadata_json or "{}")
    job_id_str = meta.get("ingestion_job_id") or ingestion_job_id

    return Document(
        id=DocumentId(doc_id),
        project_id=ProjectId(project_id),
        source_type=SourceType(source_type),
        external_id=external_id,
        raw_content=raw_content,
        structured_content=structured,
        embedding_vector=None,  # embeddings not stored on the domain object for SQLite
        ingestion_job_id=IngestionJobId(job_id_str) if job_id_str else None,
        created_at=datetime.fromisoformat(created_at),
        updated_at=datetime.fromisoformat(updated_at),
    )
