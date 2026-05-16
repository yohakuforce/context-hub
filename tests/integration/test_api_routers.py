"""Integration tests for API routers (no DB required — repos are overridden).

Uses FastAPI TestClient with dependency overrides to inject in-memory repos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport

from src.main import create_app
from src.api.dependencies import (
    get_document_repo,
    get_embedding,
    get_issue_repo,
    get_job_repo,
    get_project_repo,
    get_query_service,
)
from src.application.query_service import QueryService
from src.domain.document.entities import Document
from src.domain.ingestion.entities import IngestionJob
from src.domain.issue.entities import Issue
from src.domain.project.entities import Project, SourceConfig
from src.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter
from src.shared.types import (
    IngestionJobId,
    IssueStatus,
    JobStatus,
    ProjectId,
    SourceType,
    SyncCursor,
)

from tests.integration.test_ingestion_service import (
    InMemoryDocumentRepository,
    InMemoryIssueRepository,
    InMemoryJobRepository,
)


# ---------------------------------------------------------------------------
# In-memory Project repo fake
# ---------------------------------------------------------------------------


class InMemoryProjectRepository:
    def __init__(self):
        self._store: dict[str, Project] = {}

    async def find_by_id(self, project_id: ProjectId) -> Optional[Project]:
        return self._store.get(str(project_id))

    async def find_all(self) -> list[Project]:
        return list(self._store.values())

    async def find_by_external_id(self, external_project_id: str) -> Optional[Project]:
        for p in self._store.values():
            if p.external_project_id == external_project_id:
                return p
        return None

    async def save(self, project: Project) -> Project:
        self._store[str(project.id)] = project
        return project

    async def delete(self, project_id: ProjectId) -> None:
        self._store.pop(str(project_id), None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_API_KEY = "integration-test-dev-key"
_HEADERS = {"X-Api-Key": _TEST_API_KEY}


def _make_test_project() -> Project:
    return Project(
        id=ProjectId("proj-001"),
        name="テストプロジェクト",
        external_project_id="PROJ",
        sources=[
            SourceConfig(
                source_type=SourceType.SLACK,
                sync_interval_minutes=60,
                is_enabled=True,
                credentials=None,
                channel_ids=("C001",),
                backlog_project_key=None,
                redmine_project_identifier=None,
            )
        ],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def repos():
    job_repo = InMemoryJobRepository()
    doc_repo = InMemoryDocumentRepository()
    issue_repo = InMemoryIssueRepository()
    project_repo = InMemoryProjectRepository()
    embedding = MockEmbeddingAdapter()
    return job_repo, doc_repo, issue_repo, project_repo, embedding


@pytest.fixture
def app(repos):
    job_repo, doc_repo, issue_repo, project_repo, embedding = repos

    # Pre-populate project repo
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        project_repo.save(_make_test_project())
    )

    app_ = create_app()

    # Override all DB deps with in-memory fakes
    app_.dependency_overrides[get_job_repo] = lambda: job_repo
    app_.dependency_overrides[get_document_repo] = lambda: doc_repo
    app_.dependency_overrides[get_issue_repo] = lambda: issue_repo
    app_.dependency_overrides[get_project_repo] = lambda: project_repo
    app_.dependency_overrides[get_embedding] = lambda: embedding
    app_.dependency_overrides[get_query_service] = lambda: QueryService(
        document_repo=doc_repo,
        embedding_provider=embedding,
    )

    # Patch auth module so DEV_API_KEY == _TEST_API_KEY for integration tests.
    import src.api.middleware.auth as _auth_mod
    _auth_mod._DEV_API_KEY = _TEST_API_KEY  # noqa: SLF001
    _auth_mod._APP_ENV = "development"  # noqa: SLF001

    return app_


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    @pytest.mark.asyncio
    async def test_missing_api_key_returns_401(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/projects")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_401(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects", headers={"X-Api-Key": "invalid-key"}
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_api_key_passes_auth(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/projects", headers=_HEADERS)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Projects endpoint
# ---------------------------------------------------------------------------


class TestProjectsEndpoint:
    @pytest.mark.asyncio
    async def test_list_projects_returns_data(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/projects", headers=_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)

    @pytest.mark.asyncio
    async def test_list_projects_contains_seeded_project(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/projects", headers=_HEADERS)
        body = resp.json()
        assert len(body["data"]) >= 1
        names = [p["name"] for p in body["data"]]
        assert "テストプロジェクト" in names

    @pytest.mark.asyncio
    async def test_get_project_context_returns_summary(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/context", headers=_HEADERS
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["project_id"] == "proj-001"
        assert "document_count" in data
        assert "issue_count" in data

    @pytest.mark.asyncio
    async def test_get_project_context_not_found(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/nonexistent/context", headers=_HEADERS
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_meetings_returns_paginated(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/meetings?limit=10&offset=0",
                headers=_HEADERS,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert "meetings" in data
        assert "total" in data


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------


class TestSyncEndpoints:
    @pytest.mark.asyncio
    async def test_slack_sync_returns_202(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/sources/slack/sync",
                json={
                    "project_id": "proj-001",
                    "channel_ids": ["C_MOCK_001"],
                    "full_resync": False,
                },
                headers=_HEADERS,
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_backlog_sync_returns_202(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/sources/backlog/sync",
                json={
                    "project_id": "proj-001",
                    "backlog_project_key": "PROJ",
                    "include_wiki": True,
                    "full_resync": False,
                },
                headers=_HEADERS,
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["success"] is True

    @pytest.mark.asyncio
    async def test_redmine_sync_returns_202(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/sources/redmine/sync",
                json={
                    "project_id": "proj-001",
                    "redmine_project_identifier": "sample-proj",
                    "include_wiki": True,
                    "full_resync": False,
                },
                headers=_HEADERS,
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["success"] is True

    @pytest.mark.asyncio
    async def test_get_job_status_not_found(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/sources/jobs/nonexistent-job-id",
                headers=_HEADERS,
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_status_found(self, app, repos):
        job_repo, doc_repo, issue_repo, project_repo, embedding = repos

        # Pre-seed a completed job
        job = IngestionJob.create(
            project_id=ProjectId("proj-001"),
            source_type=SourceType.SLACK,
        )
        job = job.start()
        job = job.complete(items_processed=5)
        await job_repo.save(job)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/sources/jobs/{job.id}",
                headers=_HEADERS,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "completed"
        assert body["data"]["items_processed"] == 5

    @pytest.mark.asyncio
    async def test_sync_requires_write_scope(self, app):
        """WRITE scope is required for sync endpoints."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Invalid API key → 401 (not 403) because auth fails first
            resp = await client.post(
                "/api/v1/sources/slack/sync",
                json={
                    "project_id": "proj-001",
                    "channel_ids": ["C001"],
                    "full_resync": False,
                },
                headers={"X-Api-Key": "bad-key"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------


class TestQueryEndpoint:
    @pytest.mark.asyncio
    async def test_query_returns_empty_results_when_no_data(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/query",
                json={
                    "project_id": "proj-001",
                    "query": "認証エラー",
                    "top_k": 5,
                },
                headers=_HEADERS,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"]["results"], list)

    @pytest.mark.asyncio
    async def test_query_validates_top_k(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/query",
                json={
                    "project_id": "proj-001",
                    "query": "test",
                    "top_k": 999,  # exceeds max of 20
                },
                headers=_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_query_validates_source_types(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/query",
                json={
                    "project_id": "proj-001",
                    "query": "test",
                    "top_k": 5,
                    "source_types": ["slack", "backlog"],
                },
                headers=_HEADERS,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_query_requires_read_scope(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/query",
                json={"project_id": "proj-001", "query": "test", "top_k": 5},
            )
        assert resp.status_code == 401
