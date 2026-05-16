"""Unit tests for QueryService."""

from __future__ import annotations

import pytest
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock

from context_hub.application.query_service import QueryResult, QueryService
from context_hub.domain.document.entities import Document
from context_hub.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter
from context_hub.shared.types import (
    DocumentId,
    EmbeddingVector,
    ProjectId,
    RawContent,
    SourceType,
)


PROJECT_ID = ProjectId("test-qs-project")


def _make_document(text: str, source_type: SourceType = SourceType.SLACK) -> Document:
    return Document.create(
        project_id=PROJECT_ID,
        source_type=source_type,
        external_id=f"ext-{text[:8]}",
        raw_content=RawContent(
            text=text,
            source_url=None,
            author_id=None,
            created_at=datetime.utcnow(),
        ),
    )


class FakeDocumentRepository:
    """Minimal fake that returns controllable search results."""

    def __init__(self, results: list[tuple[Document, float]] = None):
        self._results = results or []

    async def hybrid_search(self, query_text, vector, project_id, top_k=10,
                            source_types=None, metadata_filter=None, rrf_k=60):
        filtered = self._results
        if source_types:
            filtered = [(d, s) for d, s in filtered if d.source_type in source_types]
        return filtered[:top_k]

    # Unused by QueryService but needed to satisfy type
    async def find_by_id(self, doc_id): ...
    async def find_by_project(self, *a, **k): return []
    async def find_by_external_id(self, *a, **k): return None
    async def find_similar(self, *a, **k): return []
    async def count_by_project(self, *a, **k): return 0
    async def save(self, doc): return doc


class TestQueryResult:
    def test_snippet_truncates_long_text(self):
        doc = _make_document("x" * 500)
        result = QueryResult(document=doc, score=0.9)
        assert len(result.snippet) <= 303  # 300 + "..."
        assert result.snippet.endswith("...")

    def test_snippet_short_text_no_ellipsis(self):
        doc = _make_document("short text")
        result = QueryResult(document=doc, score=0.9)
        assert result.snippet == "short text"

    def test_title_uses_summary_if_available(self):
        from context_hub.shared.types import StructuredContent
        doc = _make_document("some raw text")
        structured = StructuredContent(
            summary="Structured summary title",
            language="ja",
            tags=(),
            entities=(),
        )
        doc = doc.with_structured_content(structured)
        result = QueryResult(document=doc, score=0.9)
        assert result.title == "Structured summary title"

    def test_title_uses_first_line_of_raw_text(self):
        doc = _make_document("First line of text\nSecond line")
        result = QueryResult(document=doc, score=0.9)
        assert result.title == "First line of text"

    def test_title_truncates_at_80_chars(self):
        doc = _make_document("A" * 100)
        result = QueryResult(document=doc, score=0.9)
        assert len(result.title) <= 80


class TestQueryService:
    @pytest.fixture
    def embedding(self):
        return MockEmbeddingAdapter()

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_no_results(self, embedding):
        doc_repo = FakeDocumentRepository(results=[])
        service = QueryService(document_repo=doc_repo, embedding_provider=embedding)
        results = await service.search(PROJECT_ID, "test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_query_results(self, embedding):
        doc1 = _make_document("Slack message about authentication")
        doc2 = _make_document("Backlog issue about performance", SourceType.BACKLOG)
        fake_results = [(doc1, 0.95), (doc2, 0.80)]

        doc_repo = FakeDocumentRepository(results=fake_results)
        service = QueryService(document_repo=doc_repo, embedding_provider=embedding)

        results = await service.search(PROJECT_ID, "authentication")
        assert len(results) == 2
        assert all(isinstance(r, QueryResult) for r in results)

    @pytest.mark.asyncio
    async def test_search_respects_top_k(self, embedding):
        docs = [(d, 0.9) for d in [_make_document(f"doc {i}") for i in range(10)]]
        doc_repo = FakeDocumentRepository(results=docs)
        service = QueryService(document_repo=doc_repo, embedding_provider=embedding)

        results = await service.search(PROJECT_ID, "query", top_k=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_with_source_type_filter(self, embedding):
        slack_doc = _make_document("Slack message", SourceType.SLACK)
        backlog_doc = _make_document("Backlog issue", SourceType.BACKLOG)
        fake_results = [(slack_doc, 0.9), (backlog_doc, 0.8)]

        doc_repo = FakeDocumentRepository(results=fake_results)
        service = QueryService(document_repo=doc_repo, embedding_provider=embedding)

        results = await service.search(
            PROJECT_ID, "test", source_types=[SourceType.SLACK]
        )
        assert all(r.document.source_type == SourceType.SLACK for r in results)

    @pytest.mark.asyncio
    async def test_search_scores_are_preserved(self, embedding):
        doc = _make_document("relevant content")
        doc_repo = FakeDocumentRepository(results=[(doc, 0.876)])
        service = QueryService(document_repo=doc_repo, embedding_provider=embedding)

        results = await service.search(PROJECT_ID, "content")
        assert len(results) == 1
        assert abs(results[0].score - 0.876) < 0.001
