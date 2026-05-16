"""Unit tests for BacklogAdapter (mock mode)."""

from __future__ import annotations

import pytest

from src.infrastructure.adapters.backlog.adapter import BacklogAdapter
from src.shared.types import (
    IssueStatus,
    IssuePriority,
    ProjectId,
    SourceType,
    SyncCursor,
)


PROJECT_ID = ProjectId("test-project-backlog")


class TestBacklogAdapterMockMode:
    @pytest.fixture
    def adapter(self):
        return BacklogAdapter(
            space_key="dummy-space",
            api_key="dummy-key",
            backlog_project_key="PROJ",
            include_wiki=True,
            ingest_mode="mock",
        )

    @pytest.fixture
    def adapter_no_wiki(self):
        return BacklogAdapter(
            space_key="dummy-space",
            api_key="dummy-key",
            backlog_project_key="PROJ",
            include_wiki=False,
            ingest_mode="mock",
        )

    @pytest.mark.asyncio
    async def test_source_type_is_backlog(self, adapter):
        assert adapter.source_type == SourceType.BACKLOG

    @pytest.mark.asyncio
    async def test_fetch_returns_issues(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        assert len(result.issues) > 0

    @pytest.mark.asyncio
    async def test_issues_have_backlog_source_type(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        for issue in result.issues:
            assert issue.source_type == SourceType.BACKLOG

    @pytest.mark.asyncio
    async def test_issues_have_valid_status(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        valid_statuses = set(IssueStatus)
        for issue in result.issues:
            assert issue.status in valid_statuses

    @pytest.mark.asyncio
    async def test_issues_have_valid_priority(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        valid_priorities = set(IssuePriority)
        for issue in result.issues:
            assert issue.priority in valid_priorities

    @pytest.mark.asyncio
    async def test_issues_have_non_empty_title(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        for issue in result.issues:
            assert issue.title.strip() != ""

    @pytest.mark.asyncio
    async def test_issues_have_comments(self, adapter):
        """Fixture issues should have comments from issue_comments.json."""
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        total_comments = sum(len(i.comments) for i in result.issues)
        assert total_comments > 0

    @pytest.mark.asyncio
    async def test_fetch_returns_wiki_documents(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        assert len(result.documents) > 0

    @pytest.mark.asyncio
    async def test_wiki_documents_have_backlog_source_type(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        for doc in result.documents:
            assert doc.source_type == SourceType.BACKLOG

    @pytest.mark.asyncio
    async def test_no_wiki_returns_no_documents(self, adapter_no_wiki):
        result = await adapter_no_wiki.fetch(PROJECT_ID, cursor=None)
        assert result.documents == []

    @pytest.mark.asyncio
    async def test_cursor_advances(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        assert result.new_cursor is not None
        assert result.new_cursor.source_type == SourceType.BACKLOG
        assert result.new_cursor.cursor_value != ""

    @pytest.mark.asyncio
    async def test_issues_have_correct_project_id(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        for issue in result.issues:
            assert issue.project_id == PROJECT_ID

    @pytest.mark.asyncio
    async def test_issues_with_assignee(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        issues_with_assignee = [i for i in result.issues if i.assignee is not None]
        assert len(issues_with_assignee) > 0


class TestBacklogAdapterLiveModeNotCalled:
    """Verify live mode requires credentials but doesn't call real API."""

    def test_mock_mode_does_not_create_live_client(self):
        adapter = BacklogAdapter(
            space_key="sp",
            api_key="key",
            backlog_project_key="PROJ",
            ingest_mode="mock",
        )
        assert adapter._live_client is None

    def test_live_mode_creates_client(self):
        adapter = BacklogAdapter(
            space_key="sp",
            api_key="key",
            backlog_project_key="PROJ",
            ingest_mode="live",
        )
        assert adapter._live_client is not None
