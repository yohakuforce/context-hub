"""Unit tests for PostgresDocumentRepository mapping logic."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from context_hub.domain.document.entities import Document
from context_hub.infrastructure.db.document_repository import (
    _domain_to_values,
    _format_vector,
    _row_to_domain,
    PostgresDocumentRepository,
)
from context_hub.infrastructure.db.models import DocumentRow
from context_hub.shared.types import (
    DocumentId,
    EmbeddingVector,
    ProjectId,
    RawContent,
    SourceType,
    StructuredContent,
    ExtractedEntity,
    EntityType,
    IngestionJobId,
)


def _make_raw_content() -> RawContent:
    return RawContent(
        text="Sample text content",
        source_url="https://example.com/slack/msg",
        author_id="U001",
        created_at=datetime(2026, 5, 1, 9, 0, 0),
    )


def _make_document(with_embedding: bool = False) -> Document:
    doc = Document.create(
        project_id=ProjectId("proj-001"),
        source_type=SourceType.SLACK,
        external_id="slack-msg-001",
        raw_content=_make_raw_content(),
    )
    if with_embedding:
        vector = EmbeddingVector(
            values=tuple(0.1 for _ in range(1024)),
            model_name="BAAI/bge-m3",
            dimensions=1024,
        )
        doc = doc.with_embedding(vector)
    return doc


def _make_document_row(doc: Document) -> DocumentRow:
    row = DocumentRow()
    row.id = str(doc.id)
    row.project_id = str(doc.project_id)
    row.source_type = doc.source_type.value
    row.external_id = doc.external_id
    row.raw_text = doc.raw_content.text
    row.source_url = doc.raw_content.source_url
    row.author_id = doc.raw_content.author_id
    row.raw_created_at = doc.raw_content.created_at
    row.summary = None
    row.language = None
    row.tags = None
    row.entities = None
    row.embedding = None
    row.embedding_model = None
    row.content_tsv = None
    row.metadata_ = {}
    row.ingestion_job_id = None
    row.created_at = doc.created_at
    row.updated_at = doc.updated_at
    return row


class TestFormatVector:
    def test_basic_format(self) -> None:
        values = (0.1, 0.2, 0.3)
        result = _format_vector(values)
        assert result == "[0.1,0.2,0.3]"

    def test_single_value(self) -> None:
        result = _format_vector((1.0,))
        assert result == "[1.0]"


class TestDomainToValues:
    def test_basic_document_no_embedding(self) -> None:
        doc = _make_document()
        values = _domain_to_values(doc)
        assert values["id"] == str(doc.id)
        assert values["project_id"] == str(doc.project_id)
        assert values["source_type"] == "slack"
        assert values["raw_text"] == "Sample text content"
        assert values["embedding"] is None
        assert values["embedding_model"] is None

    def test_document_with_embedding(self) -> None:
        doc = _make_document(with_embedding=True)
        values = _domain_to_values(doc)
        assert values["embedding"] is not None
        assert len(values["embedding"]) == 1024
        assert values["embedding_model"] == "BAAI/bge-m3"

    def test_document_with_structured_content(self) -> None:
        doc = _make_document()
        doc = doc.with_structured_content(
            StructuredContent(
                summary="This is a summary",
                language="ja",
                tags=("slack", "project"),
                entities=(
                    ExtractedEntity(name="koya", entity_type=EntityType.PERSON),
                ),
            )
        )
        values = _domain_to_values(doc)
        assert values["summary"] == "This is a summary"
        assert values["language"] == "ja"
        assert "slack" in values["tags"]
        assert len(values["entities"]) == 1
        assert values["entities"][0]["name"] == "koya"


class TestRowToDomain:
    def test_basic_row_to_domain(self) -> None:
        doc = _make_document()
        row = _make_document_row(doc)
        result = _row_to_domain(row)
        assert result.id == doc.id
        assert result.project_id == doc.project_id
        assert result.source_type == SourceType.SLACK
        assert result.raw_content.text == "Sample text content"
        assert result.embedding_vector is None
        assert result.structured_content is None

    def test_row_with_embedding_to_domain(self) -> None:
        doc = _make_document(with_embedding=True)
        row = _make_document_row(doc)
        # Simulate embedding stored as list (pgvector returns list-like)
        row.embedding = [0.1] * 1024
        row.embedding_model = "BAAI/bge-m3"
        result = _row_to_domain(row)
        assert result.embedding_vector is not None
        assert result.embedding_vector.dimensions == 1024

    def test_row_with_structured_content(self) -> None:
        doc = _make_document()
        row = _make_document_row(doc)
        row.summary = "Test summary"
        row.language = "ja"
        row.tags = ["tag1", "tag2"]
        row.entities = [{"name": "Alice", "entity_type": "person"}]
        result = _row_to_domain(row)
        assert result.structured_content is not None
        assert result.structured_content.summary == "Test summary"
        assert "tag1" in result.structured_content.tags


class TestPostgresDocumentRepository:
    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        repo = PostgresDocumentRepository(session)
        result = await repo.find_by_id(DocumentId("not-found"))
        assert result is None

    @pytest.mark.asyncio
    async def test_count_by_project_returns_integer(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        session.execute = AsyncMock(return_value=mock_result)
        repo = PostgresDocumentRepository(session)
        count = await repo.count_by_project(ProjectId("proj-001"))
        assert count == 42
