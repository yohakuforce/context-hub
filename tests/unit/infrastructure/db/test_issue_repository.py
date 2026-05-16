"""Unit tests for PostgresIssueRepository mapping logic."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from context_hub.domain.issue.entities import Comment, Issue
from context_hub.infrastructure.db.issue_repository import (
    _domain_to_values,
    _row_to_domain,
    PostgresIssueRepository,
)
from context_hub.infrastructure.db.models import IssueRow
from context_hub.shared.types import (
    CommentId,
    EmbeddingVector,
    IssueId,
    IssuePriority,
    IssueStatus,
    MemberRef,
    ProjectId,
    SourceType,
)


def _make_issue() -> Issue:
    return Issue.create(
        project_id=ProjectId("proj-001"),
        source_type=SourceType.BACKLOG,
        external_id="PROJ-123",
        title="Fix the bug",
        description="The bug breaks everything",
        status=IssueStatus.OPEN,
        priority=IssuePriority.HIGH,
        assignee=MemberRef(external_id="U001", name="Alice"),
        labels=["backend", "critical"],
    )


def _make_issue_row(issue: Issue) -> IssueRow:
    row = IssueRow()
    row.id = str(issue.id)
    row.project_id = str(issue.project_id)
    row.source_type = issue.source_type.value
    row.external_id = issue.external_id
    row.title = issue.title
    row.description = issue.description
    row.status = issue.status.value
    row.priority = issue.priority.value
    row.assignee_external_id = issue.assignee.external_id if issue.assignee else None
    row.assignee_name = issue.assignee.name if issue.assignee else None
    row.due_date = None
    row.labels = issue.labels
    row.comments = []
    row.embedding = None
    row.embedding_model = None
    row.content_tsv = None
    row.metadata_ = {}
    row.created_at = issue.created_at
    row.updated_at = issue.updated_at
    return row


class TestDomainToValues:
    def test_basic_issue(self) -> None:
        issue = _make_issue()
        values = _domain_to_values(issue)
        assert values["id"] == str(issue.id)
        assert values["source_type"] == "backlog"
        assert values["status"] == "open"
        assert values["priority"] == "high"
        assert values["assignee_external_id"] == "U001"
        assert values["assignee_name"] == "Alice"
        assert values["embedding"] is None

    def test_issue_with_embedding(self) -> None:
        issue = _make_issue()
        vector = EmbeddingVector(
            values=tuple(0.5 for _ in range(1024)),
            model_name="BAAI/bge-m3",
            dimensions=1024,
        )
        issue_with_vec = issue.with_embedding(vector)
        values = _domain_to_values(issue_with_vec)
        assert values["embedding"] is not None
        assert len(values["embedding"]) == 1024

    def test_comments_serialised(self) -> None:
        issue = _make_issue()
        comment = Comment.create(
            source_type=SourceType.BACKLOG,
            external_id="comment-001",
            author=MemberRef(external_id="U002", name="Bob"),
            body="This is a comment",
            created_at=datetime(2026, 5, 1, 10, 0),
        )
        issue_with_comment = issue.with_comments([comment])
        values = _domain_to_values(issue_with_comment)
        assert len(values["comments"]) == 1
        assert values["comments"][0]["body"] == "This is a comment"

    def test_no_assignee(self) -> None:
        issue = Issue.create(
            project_id=ProjectId("proj-001"),
            source_type=SourceType.REDMINE,
            external_id="42",
            title="Unassigned issue",
            description="",
            status=IssueStatus.OPEN,
            priority=IssuePriority.NORMAL,
        )
        values = _domain_to_values(issue)
        assert values["assignee_external_id"] is None
        assert values["assignee_name"] is None


class TestRowToDomain:
    def test_basic_row_to_domain(self) -> None:
        issue = _make_issue()
        row = _make_issue_row(issue)
        result = _row_to_domain(row)
        assert result.id == issue.id
        assert result.title == "Fix the bug"
        assert result.status == IssueStatus.OPEN
        assert result.priority == IssuePriority.HIGH
        assert result.assignee is not None
        assert result.assignee.name == "Alice"
        assert "backend" in result.labels

    def test_row_without_assignee(self) -> None:
        issue = Issue.create(
            project_id=ProjectId("proj-001"),
            source_type=SourceType.REDMINE,
            external_id="99",
            title="No assignee",
            description="",
            status=IssueStatus.CLOSED,
            priority=IssuePriority.LOW,
        )
        row = _make_issue_row(issue)
        result = _row_to_domain(row)
        assert result.assignee is None

    def test_row_with_comment(self) -> None:
        issue = _make_issue()
        row = _make_issue_row(issue)
        row.comments = [
            {
                "id": "comment-001",
                "source_type": "backlog",
                "external_id": "c-001",
                "author_external_id": "U002",
                "author_name": "Bob",
                "body": "Looks good",
                "created_at": "2026-05-01T10:00:00",
            }
        ]
        result = _row_to_domain(row)
        assert len(result.comments) == 1
        assert result.comments[0].body == "Looks good"


class TestPostgresIssueRepository:
    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        repo = PostgresIssueRepository(session)
        result = await repo.find_by_id(IssueId("not-found"))
        assert result is None

    @pytest.mark.asyncio
    async def test_count_by_project(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 7
        session.execute = AsyncMock(return_value=mock_result)
        repo = PostgresIssueRepository(session)
        count = await repo.count_by_project(ProjectId("proj-001"))
        assert count == 7
