"""Tests for SqliteIssueRepository."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
import sqlite_vec

from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
from context_hub.domain.issue.entities import Issue
from context_hub.domain.project.entities import Project
from context_hub.shared.types import (
    IssueId,
    IssuePriority,
    IssueStatus,
    ProjectId,
    SourceType,
    new_id,
)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "issue_test.db")
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    schema = (
        Path(__file__).parent.parent.parent.parent.parent
        / "context_hub" / "_sqlite_schema" / "001_init.sql"
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
    await SqliteProjectRepository(db_path).save(project)
    return pid


def _make_issue(project_id: ProjectId, external_id: str = "ext-1") -> Issue:
    return Issue.create(
        project_id=project_id,
        source_type=SourceType.BACKLOG,
        external_id=external_id,
        title="Test Issue",
        description="Test description",
        status=IssueStatus.OPEN,
        priority=IssuePriority.NORMAL,
    )


@pytest.mark.asyncio
class TestSqliteIssueRepository:
    async def test_find_by_id_returns_none_when_missing(
        self, db_path: str
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        result = await repo.find_by_id(IssueId(new_id()))
        assert result is None

    async def test_save_and_find_by_id(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        issue = _make_issue(project_id)
        await repo.save(issue)
        found = await repo.find_by_id(issue.id)
        assert found is not None
        assert found.id == issue.id
        assert found.title == "Test Issue"

    async def test_find_by_project_returns_issues(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        issue1 = _make_issue(project_id, external_id="i1")
        issue2 = _make_issue(project_id, external_id="i2")
        await repo.save(issue1)
        await repo.save(issue2)
        results = await repo.find_by_project(project_id)
        ids = [i.id for i in results]
        assert issue1.id in ids
        assert issue2.id in ids

    async def test_find_by_project_status_filter(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        open_issue = _make_issue(project_id, external_id="open-1")
        closed_issue = Issue.create(
            project_id=project_id,
            source_type=SourceType.BACKLOG,
            external_id="closed-1",
            title="Closed Issue",
            description="desc",
            status=IssueStatus.CLOSED,
            priority=IssuePriority.LOW,
        )
        await repo.save(open_issue)
        await repo.save(closed_issue)
        results = await repo.find_by_project(project_id, status=IssueStatus.OPEN)
        assert all(i.status == IssueStatus.OPEN for i in results)

    async def test_find_by_project_source_type_filter(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        backlog = _make_issue(project_id, external_id="b1")
        redmine = Issue.create(
            project_id=project_id,
            source_type=SourceType.REDMINE,
            external_id="r1",
            title="Redmine Issue",
            description="desc",
            status=IssueStatus.OPEN,
            priority=IssuePriority.NORMAL,
        )
        await repo.save(backlog)
        await repo.save(redmine)
        results = await repo.find_by_project(
            project_id, source_type=SourceType.BACKLOG
        )
        assert all(i.source_type == SourceType.BACKLOG for i in results)

    async def test_find_updated_since(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        old_issue = _make_issue(project_id, external_id="old-1")
        await repo.save(old_issue)
        cutoff = datetime.utcnow()
        import asyncio
        await asyncio.sleep(0.01)
        recent_issue = _make_issue(project_id, external_id="recent-1")
        await repo.save(recent_issue)
        results = await repo.find_updated_since(
            project_id, SourceType.BACKLOG, cutoff
        )
        ids = [i.id for i in results]
        assert recent_issue.id in ids

    async def test_find_by_external_id(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        issue = _make_issue(project_id, external_id="unique-ext")
        await repo.save(issue)
        found = await repo.find_by_external_id(
            project_id, SourceType.BACKLOG, "unique-ext"
        )
        assert found is not None
        assert found.id == issue.id

    async def test_find_by_external_id_returns_none(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        result = await repo.find_by_external_id(
            project_id, SourceType.BACKLOG, "nonexistent"
        )
        assert result is None

    async def test_count_by_project(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        for i in range(3):
            await repo.save(_make_issue(project_id, external_id=f"c{i}"))
        count = await repo.count_by_project(project_id)
        assert count == 3

    async def test_count_by_project_source_type(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        await repo.save(_make_issue(project_id, external_id="b1"))
        redmine = Issue.create(
            project_id=project_id,
            source_type=SourceType.REDMINE,
            external_id="r1",
            title="Redmine",
            description="desc",
            status=IssueStatus.OPEN,
            priority=IssuePriority.NORMAL,
        )
        await repo.save(redmine)
        count = await repo.count_by_project(project_id, source_type=SourceType.BACKLOG)
        assert count == 1

    async def test_save_is_upsert(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        issue = _make_issue(project_id, external_id="upsert-ext")
        await repo.save(issue)
        updated = Issue.create(
            project_id=project_id,
            source_type=SourceType.BACKLOG,
            external_id="upsert-ext",
            title="Updated Title",
            description="desc",
            status=IssueStatus.CLOSED,
            priority=IssuePriority.LOW,
        )
        await repo.save(updated)
        count = await repo.count_by_project(project_id)
        assert count == 1

    async def test_save_many(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIssueRepository(db_path)
        issues = [_make_issue(project_id, external_id=f"batch-{i}") for i in range(3)]
        saved = await repo.save_many(issues)
        assert len(saved) == 3
        count = await repo.count_by_project(project_id)
        assert count == 3

    async def test_find_by_project_assignee_filter(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        """find_by_project with assignee_id filter."""
        from context_hub.shared.types import MemberRef
        repo = SqliteIssueRepository(db_path)
        assigned = _make_issue(project_id, external_id="assigned-1")
        # Manually set assignee
        assigned_with_assignee = Issue(
            id=assigned.id,
            project_id=assigned.project_id,
            source_type=assigned.source_type,
            external_id=assigned.external_id,
            title=assigned.title,
            description=assigned.description,
            status=assigned.status,
            priority=assigned.priority,
            assignee=MemberRef(external_id="user-42", name="Alice"),
            due_date=None,
            comments=[],
            labels=[],
            embedding_vector=None,
            created_at=assigned.created_at,
            updated_at=assigned.updated_at,
        )
        await repo.save(assigned_with_assignee)
        unassigned = _make_issue(project_id, external_id="unassigned-1")
        await repo.save(unassigned)
        results = await repo.find_by_project(project_id, assignee_id="user-42")
        assert len(results) == 1
        assert results[0].assignee is not None
        assert results[0].assignee.external_id == "user-42"
