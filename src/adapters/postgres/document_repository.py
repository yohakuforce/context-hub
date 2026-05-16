"""PostgreSQL + pgvector implementation of DocumentRepository.

Hybrid search strategy:
  1. tsvector full-text search (GIN index)
  2. pgvector cosine similarity (HNSW index)
  3. RRF (Reciprocal Rank Fusion) merge

The hybrid_search method executes two CTEs and fuses their ranks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.document.entities import Document
from src.domain.document.repository import DocumentRepository
from src.infrastructure.db.models import DocumentRow
from src.shared.types import (
    DocumentId,
    EmbeddingVector,
    ExtractedEntity,
    EntityType,
    IngestionJobId,
    ProjectId,
    RawContent,
    SourceType,
    StructuredContent,
)

# RRF constant — 60 is the de-facto standard
_RRF_K = 60

# Maximum k to prevent DoS via unbounded queries (consistent with SQLite backend).
_MAX_K: int = 1000


class PostgresDocumentRepository(DocumentRepository):
    """Concrete Document repository backed by PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def find_by_id(self, doc_id: DocumentId) -> Optional[Document]:
        row = await self._session.get(DocumentRow, str(doc_id))
        return _row_to_domain(row) if row else None

    async def find_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Document]:
        q = (
            select(DocumentRow)
            .where(DocumentRow.project_id == str(project_id))
            .order_by(DocumentRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if source_type:
            q = q.where(DocumentRow.source_type == source_type.value)
        result = await self._session.execute(q)
        return [_row_to_domain(r) for r in result.scalars().all()]

    async def find_by_external_id(
        self,
        project_id: ProjectId,
        source_type: SourceType,
        external_id: str,
    ) -> Optional[Document]:
        result = await self._session.execute(
            select(DocumentRow).where(
                DocumentRow.project_id == str(project_id),
                DocumentRow.source_type == source_type.value,
                DocumentRow.external_id == external_id,
            )
        )
        row = result.scalar_one_or_none()
        return _row_to_domain(row) if row else None

    async def find_similar(
        self,
        vector: EmbeddingVector,
        project_id: ProjectId,
        top_k: int = 10,
        source_types: Optional[list[SourceType]] = None,
    ) -> list[tuple[Document, float]]:
        """Pure vector similarity search (cosine distance via pgvector <=>).

        top_k is capped at _MAX_K to prevent DoS via unbounded queries.
        """
        top_k = min(top_k, _MAX_K)
        vec_literal = _format_vector(vector.values)
        q = text(
            f"""
            SELECT id,
                   1 - (embedding <=> '{vec_literal}'::vector) AS score
            FROM documents
            WHERE project_id = :project_id
              AND embedding IS NOT NULL
              {"AND source_type = ANY(:source_types)" if source_types else ""}
            ORDER BY embedding <=> '{vec_literal}'::vector
            LIMIT :top_k
            """
        )
        params: dict = {"project_id": str(project_id), "top_k": top_k}
        if source_types:
            params["source_types"] = [st.value for st in source_types]

        result = await self._session.execute(q, params)
        rows_with_scores = result.fetchall()

        docs = []
        for row_id, score in rows_with_scores:
            doc_row = await self._session.get(DocumentRow, row_id)
            if doc_row:
                docs.append((_row_to_domain(doc_row), float(score)))
        return docs

    async def hybrid_search(
        self,
        query_text: str,
        vector: EmbeddingVector,
        project_id: ProjectId,
        top_k: int = 10,
        source_types: Optional[list[SourceType]] = None,
        metadata_filter: Optional[dict] = None,
        rrf_k: int = _RRF_K,
    ) -> list[tuple[Document, float]]:
        """Hybrid search: tsvector + pgvector + JSONB metadata, fused via RRF.

        Returns documents ordered by descending RRF score.
        top_k is capped at _MAX_K to prevent DoS via unbounded queries.
        """
        top_k = min(top_k, _MAX_K)
        vec_literal = _format_vector(vector.values)
        source_filter = (
            "AND source_type = ANY(:source_types)" if source_types else ""
        )
        meta_filter = (
            "AND metadata @> :metadata_filter::jsonb" if metadata_filter else ""
        )

        sql = text(
            f"""
            WITH fts AS (
                SELECT id,
                       ROW_NUMBER() OVER (ORDER BY ts_rank(content_tsv,
                           plainto_tsquery('simple', :query_text)) DESC) AS rank
                FROM documents
                WHERE project_id = :project_id
                  AND content_tsv IS NOT NULL
                  AND content_tsv @@ plainto_tsquery('simple', :query_text)
                  {source_filter}
                  {meta_filter}
                LIMIT :candidate_k
            ),
            vec AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           ORDER BY embedding <=> '{vec_literal}'::vector
                       ) AS rank
                FROM documents
                WHERE project_id = :project_id
                  AND embedding IS NOT NULL
                  {source_filter}
                  {meta_filter}
                LIMIT :candidate_k
            ),
            rrf AS (
                SELECT
                    COALESCE(fts.id, vec.id) AS id,
                    COALESCE(1.0 / ({rrf_k} + fts.rank), 0)
                    + COALESCE(1.0 / ({rrf_k} + vec.rank), 0) AS rrf_score
                FROM fts
                FULL OUTER JOIN vec ON fts.id = vec.id
            )
            SELECT id, rrf_score
            FROM rrf
            ORDER BY rrf_score DESC
            LIMIT :top_k
            """
        )

        params: dict = {
            "query_text": query_text,
            "project_id": str(project_id),
            "candidate_k": top_k * 3,  # over-fetch for RRF merge quality
            "top_k": top_k,
        }
        if source_types:
            params["source_types"] = [st.value for st in source_types]
        if metadata_filter:
            params["metadata_filter"] = metadata_filter

        result = await self._session.execute(sql, params)
        rows_with_scores = result.fetchall()

        docs = []
        for row_id, score in rows_with_scores:
            doc_row = await self._session.get(DocumentRow, row_id)
            if doc_row:
                docs.append((_row_to_domain(doc_row), float(score)))
        return docs

    async def count_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
    ) -> int:
        q = select(func.count()).where(
            DocumentRow.project_id == str(project_id)
        )
        if source_type:
            q = q.where(DocumentRow.source_type == source_type.value)
        result = await self._session.execute(q)
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def save(self, document: Document) -> Document:
        """Upsert on (project_id, source_type, external_id)."""
        values = _domain_to_values(document)
        stmt = (
            pg_insert(DocumentRow)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["project_id", "source_type", "external_id"],
                set_={
                    "raw_text": values["raw_text"],
                    "source_url": values["source_url"],
                    "author_id": values["author_id"],
                    "raw_created_at": values["raw_created_at"],
                    "summary": values["summary"],
                    "language": values["language"],
                    "tags": values["tags"],
                    "entities": values["entities"],
                    "embedding": values["embedding"],
                    "embedding_model": values["embedding_model"],
                    "metadata_": values["metadata_"],
                    "updated_at": values["updated_at"],
                },
            )
        )
        await self._session.execute(stmt)
        return document


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _domain_to_values(doc: Document) -> dict:
    embedding_val = None
    embedding_model = None
    if doc.embedding_vector:
        embedding_val = list(doc.embedding_vector.values)
        embedding_model = doc.embedding_vector.model_name

    summary = None
    language = None
    tags = None
    entities = None
    if doc.structured_content:
        summary = doc.structured_content.summary
        language = doc.structured_content.language
        tags = list(doc.structured_content.tags)
        entities = [
            {"name": e.name, "entity_type": e.entity_type.value}
            for e in doc.structured_content.entities
        ]

    return {
        "id": str(doc.id),
        "project_id": str(doc.project_id),
        "source_type": doc.source_type.value,
        "external_id": doc.external_id,
        "raw_text": doc.raw_content.text,
        "source_url": doc.raw_content.source_url,
        "author_id": doc.raw_content.author_id,
        "raw_created_at": doc.raw_content.created_at,
        "summary": summary,
        "language": language,
        "tags": tags,
        "entities": entities,
        "embedding": embedding_val,
        "embedding_model": embedding_model,
        "metadata_": {
            "ingestion_job_id": str(doc.ingestion_job_id) if doc.ingestion_job_id else None
        },
        "ingestion_job_id": str(doc.ingestion_job_id) if doc.ingestion_job_id else None,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def _row_to_domain(row: DocumentRow) -> Document:
    from src.shared.types import new_id  # local import to avoid circular

    raw_content = RawContent(
        text=row.raw_text,
        source_url=row.source_url,
        author_id=row.author_id,
        created_at=row.raw_created_at or row.created_at,
    )

    structured = None
    if row.summary is not None:
        entities_raw = row.entities or []
        extracted = tuple(
            ExtractedEntity(
                name=e["name"],
                entity_type=EntityType(e["entity_type"]),
            )
            for e in entities_raw
        )
        structured = StructuredContent(
            summary=row.summary,
            language=row.language or "ja",
            tags=tuple(row.tags or []),
            entities=extracted,
        )

    embedding = None
    if row.embedding is not None:
        vec_values = tuple(float(v) for v in row.embedding)
        embedding = EmbeddingVector(
            values=vec_values,
            model_name=row.embedding_model or "unknown",
            dimensions=len(vec_values),
        )

    meta = row.metadata_ or {}
    job_id_str = meta.get("ingestion_job_id") or (
        str(row.ingestion_job_id) if row.ingestion_job_id else None
    )

    return Document(
        id=DocumentId(row.id),
        project_id=ProjectId(row.project_id),
        source_type=SourceType(row.source_type),
        external_id=row.external_id,
        raw_content=raw_content,
        structured_content=structured,
        embedding_vector=embedding,
        ingestion_job_id=IngestionJobId(job_id_str) if job_id_str else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _format_vector(values: tuple[float, ...]) -> str:
    """Convert tuple to pgvector literal string '[0.1,0.2,...]'."""
    return "[" + ",".join(str(v) for v in values) + "]"
