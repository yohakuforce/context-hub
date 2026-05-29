"""Integration tests for the issues REST endpoints.

GET /api/v1/projects/{projectId}/issues
GET /api/v1/projects/{projectId}/issues/{issueId}

Uses FastAPI TestClient with dependency_overrides (in-memory repos) and
asserts camelCase response keys per the wire contract.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient

from context_hub.main import create_app
from context_hub.api.dependencies import (
    get_document_repo,
    get_embedding,
    get_issue_repo,
    get_job_repo,
    get_project_repo,
    get_query_service,
)
from context_hub.application.query_service import QueryService
from context_hub.domain.issue.entities import Comment, Issue
from context_hub.domain.project.entities import Project, SourceConfig
from context_hub.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter
from context_hub.shared.types import (
    CommentId,
    IssueId,
    IssuePriority,
    IssueStatus,
    MemberRef,
    ProjectId,
    SourceType,
)

from tests.integration.test_ingestion_service import (
    InMemoryDocumentRepository,
    InMemoryIssueRepository,
    InMemoryJobRepository,
)
from tests.integration.test_api_routers import InMemoryProjectRepository


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_TEST_API_KEY = "integration-test-dev-key"
_HEADERS = {"X-Api-Key": _TEST_API_KEY}


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_project() -> Project:
    return Project(
        id=ProjectId("proj-001"),
        name="テストプロジェクト",
        external_project_id="PROJ",
        sources=[
            SourceConfig(
                source_type=SourceType.BACKLOG,
                sync_interval_minutes=60,
                is_enabled=True,
                credentials=None,
                channel_ids=(),
                backlog_project_key="PROJ",
                redmine_project_identifier=None,
            )
        ],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _make_backlog_issue(
    issue_id: str = "issue-001",
    external_id: str = "BLG-1",
    title: str = "Fix login bug",
    status: IssueStatus = IssueStatus.OPEN,
    assignee: Optional[MemberRef] = None,
    comments: Optional[list[Comment]] = None,
) -> Issue:
    return Issue(
        id=IssueId(issue_id),
        project_id=ProjectId("proj-001"),
        source_type=SourceType.BACKLOG,
        external_id=external_id,
        title=title,
        description="Detailed description of the issue.",
        status=status,
        priority=IssuePriority.HIGH,
        assignee=assignee or MemberRef(external_id="user-1", name="Alice"),
        due_date=date(2026, 6, 30),
        comments=comments or [],
        labels=["bug", "auth"],
        embedding_vector=None,
        created_at=datetime(2026, 1, 10),
        updated_at=datetime(2026, 2, 15),
    )


def _make_comment(comment_id: str = "cmt-001") -> Comment:
    return Comment(
        id=CommentId(comment_id),
        source_type=SourceType.BACKLOG,
        external_id=comment_id,
        author=MemberRef(external_id="user-2", name="Bob"),
        body="This looks like a regression.",
        created_at=datetime(2026, 2, 1),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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

    asyncio.run(project_repo.save(_make_project()))

    app_ = create_app()

    app_.dependency_overrides[get_job_repo] = lambda: job_repo
    app_.dependency_overrides[get_document_repo] = lambda: doc_repo
    app_.dependency_overrides[get_issue_repo] = lambda: issue_repo
    app_.dependency_overrides[get_project_repo] = lambda: project_repo
    app_.dependency_overrides[get_embedding] = lambda: embedding
    app_.dependency_overrides[get_query_service] = lambda: QueryService(
        document_repo=doc_repo,
        embedding_provider=embedding,
    )

    import context_hub.api.middleware.auth as _auth_mod
    _auth_mod._DEV_API_KEY = _TEST_API_KEY  # noqa: SLF001
    _auth_mod._APP_ENV = "development"  # noqa: SLF001

    return app_


# ---------------------------------------------------------------------------
# list_issues: basic shape
# ---------------------------------------------------------------------------


class TestListIssues:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_issues(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues?source=backlog",
                headers=_HEADERS,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["issues"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_seeded_issues(self, app, repos):
        _, _, issue_repo, _, _ = repos
        issue = _make_backlog_issue()
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues?source=backlog",
                headers=_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["issues"]) == 1
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_response_keys_are_camel_case(self, app, repos):
        """Wire format must use camelCase keys per 02-api-spec.md contract."""
        _, _, issue_repo, _, _ = repos
        issue = _make_backlog_issue()
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues?source=backlog",
                headers=_HEADERS,
            )
        data = resp.json()["data"]
        issue_data = data["issues"][0]

        # camelCase keys MUST be present
        assert "sourceType" in issue_data
        assert "externalId" in issue_data
        assert "commentCount" in issue_data
        assert "createdAt" in issue_data
        assert "updatedAt" in issue_data
        assert "dueDate" in issue_data

        # snake_case keys must NOT be present
        assert "source_type" not in issue_data
        assert "external_id" not in issue_data
        assert "comment_count" not in issue_data
        assert "created_at" not in issue_data
        assert "updated_at" not in issue_data
        assert "due_date" not in issue_data

    @pytest.mark.asyncio
    async def test_issue_field_values_are_correct(self, app, repos):
        _, _, issue_repo, _, _ = repos
        issue = _make_backlog_issue(
            issue_id="issue-abc",
            external_id="BLG-99",
            title="重要なバグ修正",
        )
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues?source=backlog",
                headers=_HEADERS,
            )
        issue_data = resp.json()["data"]["issues"][0]

        assert issue_data["id"] == "issue-abc"
        assert issue_data["externalId"] == "BLG-99"
        assert issue_data["sourceType"] == "backlog"
        assert issue_data["title"] == "重要なバグ修正"
        assert issue_data["status"] == "open"
        assert issue_data["priority"] == "high"
        assert issue_data["dueDate"] == "2026-06-30"
        assert issue_data["labels"] == ["bug", "auth"]
        assert issue_data["assignee"]["externalId"] == "user-1"
        assert issue_data["assignee"]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_assignee_schema_has_camel_case_keys(self, app, repos):
        _, _, issue_repo, _, _ = repos
        await issue_repo.save(_make_backlog_issue())

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues?source=backlog",
                headers=_HEADERS,
            )
        assignee = resp.json()["data"]["issues"][0]["assignee"]
        assert "externalId" in assignee
        assert "external_id" not in assignee

    @pytest.mark.asyncio
    async def test_issue_without_assignee_has_null(self, app, repos):
        _, _, issue_repo, _, _ = repos
        issue = _make_backlog_issue(assignee=None)
        issue = Issue(
            id=issue.id,
            project_id=issue.project_id,
            source_type=issue.source_type,
            external_id=issue.external_id,
            title=issue.title,
            description=issue.description,
            status=issue.status,
            priority=issue.priority,
            assignee=None,
            due_date=issue.due_date,
            comments=issue.comments,
            labels=issue.labels,
            embedding_vector=None,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
        )
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues?source=backlog",
                headers=_HEADERS,
            )
        issue_data = resp.json()["data"]["issues"][0]
        assert issue_data["assignee"] is None

    @pytest.mark.asyncio
    async def test_pagination_params_reflected_in_response(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues?source=backlog&limit=10&offset=5",
                headers=_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["limit"] == 10
        assert data["offset"] == 5

    @pytest.mark.asyncio
    async def test_requires_source_param(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues",
                headers=_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_source_returns_422(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues?source=jira",
                headers=_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_requires_auth(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues?source=backlog",
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# get_issue: detail
# ---------------------------------------------------------------------------


class TestGetIssue:
    @pytest.mark.asyncio
    async def test_returns_issue_detail(self, app, repos):
        _, _, issue_repo, _, _ = repos
        comment = _make_comment()
        issue = _make_backlog_issue(comments=[comment])
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/projects/proj-001/issues/{issue.id}",
                headers=_HEADERS,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["id"] == str(issue.id)
        assert data["externalId"] == "BLG-1"
        assert data["sourceType"] == "backlog"

    @pytest.mark.asyncio
    async def test_response_keys_are_camel_case(self, app, repos):
        """Detail endpoint must also return camelCase keys."""
        _, _, issue_repo, _, _ = repos
        comment = _make_comment()
        issue = _make_backlog_issue(comments=[comment])
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/projects/proj-001/issues/{issue.id}",
                headers=_HEADERS,
            )
        data = resp.json()["data"]

        assert "sourceType" in data
        assert "externalId" in data
        assert "commentCount" in data
        assert "createdAt" in data
        assert "updatedAt" in data
        assert "source_type" not in data
        assert "external_id" not in data

    @pytest.mark.asyncio
    async def test_includes_comments(self, app, repos):
        _, _, issue_repo, _, _ = repos
        comment = _make_comment("cmt-999")
        issue = _make_backlog_issue(comments=[comment])
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/projects/proj-001/issues/{issue.id}",
                headers=_HEADERS,
            )
        data = resp.json()["data"]
        assert len(data["comments"]) == 1
        c = data["comments"][0]
        assert c["body"] == "This looks like a regression."
        assert c["author"]["externalId"] == "user-2"
        assert c["createdAt"] == "2026-02-01T00:00:00"

    @pytest.mark.asyncio
    async def test_comments_have_camel_case_keys(self, app, repos):
        _, _, issue_repo, _, _ = repos
        comment = _make_comment()
        issue = _make_backlog_issue(comments=[comment])
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/projects/proj-001/issues/{issue.id}",
                headers=_HEADERS,
            )
        c = resp.json()["data"]["comments"][0]
        assert "createdAt" in c
        assert "created_at" not in c
        assert "externalId" in c["author"]
        assert "external_id" not in c["author"]

    @pytest.mark.asyncio
    async def test_include_comments_false_returns_empty_list(self, app, repos):
        _, _, issue_repo, _, _ = repos
        comment = _make_comment()
        issue = _make_backlog_issue(comments=[comment])
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/projects/proj-001/issues/{issue.id}?include_comments=false",
                headers=_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["comments"] == []

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues/no-such-issue",
                headers=_HEADERS,
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_project_returns_404(self, app, repos):
        """Issue exists but under a different project — must be 404."""
        _, _, issue_repo, _, _ = repos
        issue = Issue(
            id=IssueId("issue-xyz"),
            project_id=ProjectId("proj-other"),
            source_type=SourceType.BACKLOG,
            external_id="BLG-99",
            title="Wrong project issue",
            description="...",
            status=IssueStatus.OPEN,
            priority=IssuePriority.NORMAL,
            assignee=None,
            due_date=None,
            comments=[],
            labels=[],
            embedding_vector=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/projects/proj-001/issues/issue-xyz",
                headers=_HEADERS,
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_auth(self, app, repos):
        _, _, issue_repo, _, _ = repos
        issue = _make_backlog_issue()
        await issue_repo.save(issue)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/projects/proj-001/issues/{issue.id}",
            )
        assert resp.status_code == 401
