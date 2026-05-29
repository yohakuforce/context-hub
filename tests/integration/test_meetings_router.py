"""Integration tests for GET /api/v1/projects/{projectId}/meetings/{meetingId}.

Locks the wire contract AI-Project-Manager's HTTP client depends on:
  data.id / data.title / data.meetingAt / data.rawTranscript / data.summary
  data.extractedTasks[].title / .suggestedAssignee / .suggestedDueDate (camelCase)
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from context_hub.api.dependencies import (
    get_document_repo,
    get_embedding,
    get_issue_repo,
    get_job_repo,
    get_project_repo,
    get_query_service,
)
from context_hub.application.query_service import QueryService
from context_hub.domain.document.entities import Document, ExtractedMeetingTask
from context_hub.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter
from context_hub.main import create_app
from context_hub.shared.types import ProjectId, RawContent, SourceType

from tests.integration.test_api_routers import InMemoryProjectRepository
from tests.integration.test_ingestion_service import (
    InMemoryDocumentRepository,
    InMemoryIssueRepository,
    InMemoryJobRepository,
)
from tests.integration.test_issues_router import _make_project

_TEST_API_KEY = "integration-test-dev-key"
_HEADERS = {"X-Api-Key": _TEST_API_KEY}


def _make_meeting(meeting_id: str = "meeting-001") -> Document:
    doc = Document(
        id=meeting_id,  # type: ignore[arg-type]
        project_id=ProjectId("proj-001"),
        source_type=SourceType.MEETING,
        external_id="ext-meeting-001",
        raw_content=RawContent(
            text="定例MTG\n認証基盤のリプレースを最優先に決定。",
            source_url=None,
            author_id=None,
            created_at=datetime(2026, 5, 29, 10, 0),
        ),
        structured_content=None,
        embedding_vector=None,
        ingestion_job_id=None,
        created_at=datetime(2026, 5, 29, 10, 0),
        updated_at=datetime(2026, 5, 29, 10, 0),
        extracted_tasks=(
            ExtractedMeetingTask(title="認証APIスキーマ設計レビュー", assignee="メンバーA", due_date="2026-06-03"),
            ExtractedMeetingTask(title="マイグレーション失敗の原因特定"),
        ),
    )
    return doc


@pytest.fixture
def repos():
    return (
        InMemoryJobRepository(),
        InMemoryDocumentRepository(),
        InMemoryIssueRepository(),
        InMemoryProjectRepository(),
        MockEmbeddingAdapter(),
    )


@pytest.fixture
def app(repos):
    job_repo, doc_repo, issue_repo, project_repo, embedding = repos
    asyncio.run(project_repo.save(_make_project()))

    app_ = create_app()
    app_.dependency_overrides[get_job_repo] = lambda: job_repo
    app_.dependency_overrides[get_document_repo] = lambda: doc_repo
    app_.dependency_overrides[get_issue_repo] = lambda: issue_repo
    app_.dependency_overrides[get_project_repo] = lambda: project_repo
    app_.dependency_overrides[get_embedding] = lambda: embedding
    app_.dependency_overrides[get_query_service] = lambda: QueryService(
        document_repo=doc_repo, embedding_provider=embedding
    )

    import context_hub.api.middleware.auth as _auth_mod
    _auth_mod._DEV_API_KEY = _TEST_API_KEY  # noqa: SLF001
    _auth_mod._APP_ENV = "development"  # noqa: SLF001
    return app_


@pytest.mark.asyncio
async def test_meeting_detail_returns_camelcase_extracted_tasks(app, repos):
    _, doc_repo, _, _, _ = repos
    await doc_repo.save(_make_meeting())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/projects/proj-001/meetings/meeting-001", headers=_HEADERS
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    # Keys AI-PM's http_client reads directly (must be camelCase / present).
    assert data["id"] == "meeting-001"
    assert "title" in data and "meetingAt" in data and "rawTranscript" in data
    tasks = data["extractedTasks"]
    assert len(tasks) == 2
    assert tasks[0]["title"] == "認証APIスキーマ設計レビュー"
    assert tasks[0]["suggestedAssignee"] == "メンバーA"
    assert tasks[0]["suggestedDueDate"] == "2026-06-03"
    assert tasks[1]["suggestedAssignee"] is None


@pytest.mark.asyncio
async def test_meeting_not_found_returns_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/projects/proj-001/meetings/does-not-exist", headers=_HEADERS
        )
    assert resp.status_code == 404
