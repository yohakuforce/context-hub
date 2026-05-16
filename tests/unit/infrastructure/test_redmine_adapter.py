"""Unit tests for RedmineAdapter (mock mode)."""

from __future__ import annotations

import pytest

from src.infrastructure.adapters.redmine.adapter import RedmineAdapter
from src.shared.types import (
    IssueStatus,
    IssuePriority,
    ProjectId,
    SourceType,
)


PROJECT_ID = ProjectId("test-project-redmine")


class TestRedmineAdapterMockMode:
    @pytest.fixture
    def adapter(self):
        return RedmineAdapter(
            base_url="http://redmine.example.internal",
            api_key="dummy-key",
            redmine_project_identifier="sample-proj",
            include_wiki=True,
            ingest_mode="mock",
        )

    @pytest.fixture
    def adapter_no_wiki(self):
        return RedmineAdapter(
            base_url="http://redmine.example.internal",
            api_key="dummy-key",
            redmine_project_identifier="sample-proj",
            include_wiki=False,
            ingest_mode="mock",
        )

    @pytest.mark.asyncio
    async def test_source_type_is_redmine(self, adapter):
        assert adapter.source_type == SourceType.REDMINE

    @pytest.mark.asyncio
    async def test_fetch_returns_issues(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        assert len(result.issues) > 0

    @pytest.mark.asyncio
    async def test_issues_have_redmine_source_type(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        for issue in result.issues:
            assert issue.source_type == SourceType.REDMINE

    @pytest.mark.asyncio
    async def test_issues_have_valid_status(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        valid = set(IssueStatus)
        for issue in result.issues:
            assert issue.status in valid

    @pytest.mark.asyncio
    async def test_issues_have_valid_priority(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        valid = set(IssuePriority)
        for issue in result.issues:
            assert issue.priority in valid

    @pytest.mark.asyncio
    async def test_journals_with_notes_become_comments(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        # The first fixture issue has 2 journals with notes
        issue = next(
            (i for i in result.issues if len(i.comments) >= 2), None
        )
        assert issue is not None
        for comment in issue.comments:
            assert comment.body.strip() != ""
            assert comment.author.name != ""

    @pytest.mark.asyncio
    async def test_issue_without_journals_has_no_comments(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        # Second fixture issue has empty journals list
        no_journal_issues = [i for i in result.issues if len(i.comments) == 0]
        assert len(no_journal_issues) > 0

    @pytest.mark.asyncio
    async def test_fetch_returns_wiki_documents(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        # architecture fixture page exists
        assert len(result.documents) >= 1

    @pytest.mark.asyncio
    async def test_wiki_documents_have_redmine_source_type(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        for doc in result.documents:
            assert doc.source_type == SourceType.REDMINE

    @pytest.mark.asyncio
    async def test_no_wiki_returns_no_documents(self, adapter_no_wiki):
        result = await adapter_no_wiki.fetch(PROJECT_ID, cursor=None)
        assert result.documents == []

    @pytest.mark.asyncio
    async def test_cursor_set_after_fetch(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        assert result.new_cursor is not None
        assert result.new_cursor.source_type == SourceType.REDMINE

    @pytest.mark.asyncio
    async def test_issues_have_correct_project_id(self, adapter):
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        for issue in result.issues:
            assert issue.project_id == PROJECT_ID

    @pytest.mark.asyncio
    async def test_issue_labels_include_tracker(self, adapter):
        """Tracker name should appear in issue labels."""
        result = await adapter.fetch(PROJECT_ID, cursor=None)
        bug_issue = next(
            (i for i in result.issues if "Bug" in i.labels), None
        )
        assert bug_issue is not None


class TestRedmineAdapterClientCreation:
    def test_mock_mode_no_live_client(self):
        adapter = RedmineAdapter(
            base_url="http://redmine.example.internal",
            api_key="dummy-key",
            redmine_project_identifier="sample-proj",
            ingest_mode="mock",
        )
        assert adapter._live_client is None

    def test_live_mode_creates_client(self):
        adapter = RedmineAdapter(
            base_url="http://redmine.example.internal",
            api_key="dummy-key",
            redmine_project_identifier="sample-proj",
            ingest_mode="live",
        )
        assert adapter._live_client is not None
