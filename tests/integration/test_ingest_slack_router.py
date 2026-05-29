"""Integration tests for POST /api/v1/projects/{projectId}/ingest/slack.

Verifies scraped Slack messages upsert as slack Documents and that re-posting
the same ts is idempotent (updated, not duplicated).
"""

from __future__ import annotations

import asyncio

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
from context_hub.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter
from context_hub.main import create_app
from context_hub.shared.types import ProjectId, SourceType

from tests.integration.test_api_routers import InMemoryProjectRepository
from tests.integration.test_ingestion_service import (
    InMemoryDocumentRepository,
    InMemoryIssueRepository,
    InMemoryJobRepository,
)
from tests.integration.test_issues_router import _make_project

_HEADERS = {"X-Api-Key": "integration-test-dev-key"}


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
    _auth_mod._DEV_API_KEY = "integration-test-dev-key"  # noqa: SLF001
    _auth_mod._APP_ENV = "development"  # noqa: SLF001
    return app_


_PAYLOAD = {
    "messages": [
        {"ts": "1716800000.001", "text": "認証基盤のリプレース進めます", "user": "U1", "userName": "メンバーA"},
        {"ts": "1716800100.002", "text": "マイグレーション失敗の件、調査中", "user": "U2"},
        {"ts": "1716800200.003", "text": "   ", "user": "U3"},  # blank → skipped
    ]
}


@pytest.mark.asyncio
async def test_ingest_slack_creates_then_upserts(app, repos):
    _, doc_repo, _, _, _ = repos
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/projects/proj-001/ingest/slack", json=_PAYLOAD, headers=_HEADERS
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["ingested"] == 2
        assert data["skipped"] == 1
        assert len(data["documentIds"]) == 2

        # Stored as slack documents.
        docs = await doc_repo.find_by_project(ProjectId("proj-001"), SourceType.SLACK)
        assert len(docs) == 2

        # Re-post same ts → updated, not duplicated.
        resp2 = await client.post(
            "/api/v1/projects/proj-001/ingest/slack", json=_PAYLOAD, headers=_HEADERS
        )
        data2 = resp2.json()["data"]
        assert data2["updated"] == 2
        assert data2["ingested"] == 0
        docs_after = await doc_repo.find_by_project(ProjectId("proj-001"), SourceType.SLACK)
        assert len(docs_after) == 2


@pytest.mark.asyncio
async def test_ingest_slack_unknown_project_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/projects/nope/ingest/slack", json=_PAYLOAD, headers=_HEADERS
        )
    assert resp.status_code == 404
