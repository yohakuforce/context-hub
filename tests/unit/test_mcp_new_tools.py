"""Unit tests for newly implemented MCP tool handlers.

Covers: get_project_context, get_members, get_meeting, get_issues, get_issue_detail.

All tools are tested via module-level patching to avoid real DB/filesystem access,
mirroring the pattern used in tests/unit/test_mcp.py for search_context.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_hub.domain.issue.entities import Comment, Issue
from context_hub.domain.project.entities import Project, SourceConfig
from context_hub.shared.types import (
    CommentId,
    IssueId,
    IssuePriority,
    IssueStatus,
    MemberRef,
    ProjectId,
    SourceType,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_project(project_id: str = "proj-001") -> Project:
    return Project(
        id=ProjectId(project_id),
        name="Test Project",
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
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


_DEFAULT_ASSIGNEE = MemberRef(external_id="user-1", name="Alice")
_SENTINEL = object()


def _make_issue(
    project_id: str = "proj-001",
    source_type: SourceType = SourceType.BACKLOG,
    status: IssueStatus = IssueStatus.OPEN,
    assignee: MemberRef | None = _SENTINEL,  # type: ignore[assignment]
    comments: list[Comment] | None = None,
) -> Issue:
    resolved_assignee = _DEFAULT_ASSIGNEE if assignee is _SENTINEL else assignee
    return Issue(
        id=IssueId("issue-uuid-001"),
        project_id=ProjectId(project_id),
        source_type=source_type,
        external_id="BLG-42",
        title="Fix login bug",
        description="Users cannot log in after password reset.",
        status=status,
        priority=IssuePriority.HIGH,
        assignee=resolved_assignee,
        due_date=date(2026, 6, 1),
        comments=comments or [],
        labels=["bug", "auth"],
        embedding_vector=None,
        created_at=datetime(2026, 1, 15),
        updated_at=datetime(2026, 2, 1),
    )


def _make_comment() -> Comment:
    return Comment(
        id=CommentId("comment-uuid-001"),
        source_type=SourceType.BACKLOG,
        external_id="cmt-001",
        author=MemberRef(external_id="user-2", name="Bob"),
        body="Looks like a regression in the auth module.",
        created_at=datetime(2026, 1, 20),
    )


def _make_doc_mock(
    doc_id: str = "doc-uuid-001",
    source_type: SourceType = SourceType.MEETING,
    text: str = "Meeting transcript line 1\nLine 2",
    summary: str = "Sprint review summary",
) -> MagicMock:
    doc = MagicMock()
    doc.id = doc_id
    doc.source_type = source_type
    doc.raw_content = MagicMock()
    doc.raw_content.text = text
    doc.raw_content.created_at = datetime(2026, 3, 1)
    doc.structured_content = MagicMock()
    doc.structured_content.summary = summary
    return doc


def _make_settings_mock(db_path: str = "./data/test.db") -> MagicMock:
    settings_mock = MagicMock()
    settings_mock.ch_sqlite_db = db_path
    return settings_mock


def _make_module_patches(
    settings: MagicMock,
    project_repo: MagicMock | None = None,
    document_repo: MagicMock | None = None,
    issue_repo: MagicMock | None = None,
) -> dict[str, Any]:
    """Build sys.modules patches for SQLite adapter modules."""
    mock_profiles = MagicMock()
    mock_profiles.get_profile_settings = MagicMock(return_value=settings)

    patches: dict[str, Any] = {"context_hub.config.profiles": mock_profiles}

    if project_repo is not None:
        mock_project_repo_module = MagicMock()
        mock_project_repo_module.SqliteProjectRepository = MagicMock(return_value=project_repo)
        patches["context_hub.adapters.sqlite.project_repository"] = mock_project_repo_module

    if document_repo is not None:
        mock_doc_repo_module = MagicMock()
        mock_doc_repo_module.SqliteDocumentRepository = MagicMock(return_value=document_repo)
        patches["context_hub.adapters.sqlite.document_repository"] = mock_doc_repo_module

    if issue_repo is not None:
        mock_issue_repo_module = MagicMock()
        mock_issue_repo_module.SqliteIssueRepository = MagicMock(return_value=issue_repo)
        patches["context_hub.adapters.sqlite.issue_repository"] = mock_issue_repo_module

    return patches


# ---------------------------------------------------------------------------
# get_project_context
# ---------------------------------------------------------------------------


class TestToolGetProjectContext:
    """Tests for _tool_get_project_context."""

    @pytest.mark.asyncio
    async def test_missing_project_id_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_project_context

        result = await _tool_get_project_context({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_project_not_found_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_project_context

        project_repo = AsyncMock()
        project_repo.find_by_id = AsyncMock(return_value=None)
        document_repo = AsyncMock()
        issue_repo = AsyncMock()

        with patch.dict(
            sys.modules,
            _make_module_patches(
                _make_settings_mock(),
                project_repo=project_repo,
                document_repo=document_repo,
                issue_repo=issue_repo,
            ),
        ):
            result = await _tool_get_project_context({"projectId": "nonexistent"})

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_returns_project_summary_fields(self) -> None:
        from context_hub.mcp.server import _tool_get_project_context

        project = _make_project("proj-001")
        project_repo = AsyncMock()
        project_repo.find_by_id = AsyncMock(return_value=project)

        document_repo = AsyncMock()
        document_repo.count_by_project = AsyncMock(return_value=12)

        issue_repo = AsyncMock()
        issue_repo.count_by_project = AsyncMock(return_value=5)

        with patch.dict(
            sys.modules,
            _make_module_patches(
                _make_settings_mock(),
                project_repo=project_repo,
                document_repo=document_repo,
                issue_repo=issue_repo,
            ),
        ):
            result = await _tool_get_project_context({"projectId": "proj-001"})

        assert "error" not in result
        assert result["projectId"] == "proj-001"
        assert result["name"] == "Test Project"
        assert result["documentCount"] == 12
        assert result["issueCount"] == 5
        assert isinstance(result["activeSources"], list)
        assert "slack" in result["activeSources"]

    @pytest.mark.asyncio
    async def test_exception_returns_safe_error(self) -> None:
        from context_hub.mcp.server import _tool_get_project_context

        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(side_effect=RuntimeError("DB down"))

        with patch.dict(sys.modules, {"context_hub.config.profiles": mock_profiles}):
            result = await _tool_get_project_context({"projectId": "proj-001"})

        assert "error" in result
        assert "DB down" not in result["error"]


# ---------------------------------------------------------------------------
# get_members
# ---------------------------------------------------------------------------


class TestToolGetMembers:
    """Tests for _tool_get_members."""

    @pytest.mark.asyncio
    async def test_missing_project_id_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_members

        result = await _tool_get_members({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_returns_empty_members_when_no_issues(self) -> None:
        from context_hub.mcp.server import _tool_get_members

        issue_repo = AsyncMock()
        issue_repo.find_by_project = AsyncMock(return_value=[])

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_members({"projectId": "proj-001"})

        assert "error" not in result
        assert result["members"] == []

    @pytest.mark.asyncio
    async def test_aggregates_members_from_issues(self) -> None:
        from context_hub.mcp.server import _tool_get_members

        alice = MemberRef(external_id="user-1", name="Alice")
        issue1 = _make_issue(assignee=alice)
        issue2 = _make_issue(assignee=alice)

        issue_repo = AsyncMock()
        issue_repo.find_by_project = AsyncMock(return_value=[issue1, issue2])

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_members({"projectId": "proj-001"})

        assert "error" not in result
        members = result["members"]
        assert len(members) == 1
        assert members[0]["externalId"] == "user-1"
        assert members[0]["name"] == "Alice"
        assert members[0]["assignedIssueCount"] == 2

    @pytest.mark.asyncio
    async def test_issues_without_assignee_are_skipped(self) -> None:
        from context_hub.mcp.server import _tool_get_members

        issue_no_assignee = _make_issue(assignee=None)
        issue_repo = AsyncMock()
        issue_repo.find_by_project = AsyncMock(return_value=[issue_no_assignee])

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_members({"projectId": "proj-001"})

        assert result["members"] == []

    @pytest.mark.asyncio
    async def test_exception_returns_safe_error(self) -> None:
        from context_hub.mcp.server import _tool_get_members

        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(side_effect=RuntimeError("DB down"))

        with patch.dict(sys.modules, {"context_hub.config.profiles": mock_profiles}):
            result = await _tool_get_members({"projectId": "proj-001"})

        assert "error" in result
        assert "DB down" not in result["error"]


# ---------------------------------------------------------------------------
# get_meeting
# ---------------------------------------------------------------------------


class TestToolGetMeeting:
    """Tests for _tool_get_meeting."""

    @pytest.mark.asyncio
    async def test_missing_args_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_meeting

        result = await _tool_get_meeting({"projectId": "proj-001"})
        assert "error" in result

        result2 = await _tool_get_meeting({"meetingId": "doc-001"})
        assert "error" in result2

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_meeting

        document_repo = AsyncMock()
        document_repo.find_by_id = AsyncMock(return_value=None)

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), document_repo=document_repo),
        ):
            result = await _tool_get_meeting({"projectId": "proj-001", "meetingId": "no-such-id"})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_non_meeting_doc_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_meeting

        doc = _make_doc_mock(source_type=SourceType.SLACK)
        document_repo = AsyncMock()
        document_repo.find_by_id = AsyncMock(return_value=doc)

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), document_repo=document_repo),
        ):
            result = await _tool_get_meeting({"projectId": "proj-001", "meetingId": "doc-uuid-001"})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_returns_meeting_detail_fields(self) -> None:
        from context_hub.mcp.server import _tool_get_meeting

        doc = _make_doc_mock()
        document_repo = AsyncMock()
        document_repo.find_by_id = AsyncMock(return_value=doc)

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), document_repo=document_repo),
        ):
            result = await _tool_get_meeting({"projectId": "proj-001", "meetingId": "doc-uuid-001"})

        assert "error" not in result
        assert result["meetingId"] == "doc-uuid-001"
        assert result["projectId"] == "proj-001"
        assert result["title"] == "Sprint review summary"[:80]
        assert result["rawTranscript"] == doc.raw_content.text
        assert result["summary"] == doc.structured_content.summary
        assert result["decisions"] == []
        assert result["extractedTasks"] == []

    @pytest.mark.asyncio
    async def test_title_derived_from_first_line_when_no_summary(self) -> None:
        from context_hub.mcp.server import _tool_get_meeting

        doc = _make_doc_mock(summary="")
        doc.structured_content.summary = ""
        document_repo = AsyncMock()
        document_repo.find_by_id = AsyncMock(return_value=doc)

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), document_repo=document_repo),
        ):
            result = await _tool_get_meeting({"projectId": "proj-001", "meetingId": "doc-uuid-001"})

        assert "error" not in result
        assert result["title"] == "Meeting transcript line 1"

    @pytest.mark.asyncio
    async def test_exception_returns_safe_error(self) -> None:
        from context_hub.mcp.server import _tool_get_meeting

        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(side_effect=RuntimeError("DB down"))

        with patch.dict(sys.modules, {"context_hub.config.profiles": mock_profiles}):
            result = await _tool_get_meeting({"projectId": "p", "meetingId": "m"})

        assert "error" in result
        assert "DB down" not in result["error"]


# ---------------------------------------------------------------------------
# get_issues
# ---------------------------------------------------------------------------


class TestToolGetIssues:
    """Tests for _tool_get_issues."""

    @pytest.mark.asyncio
    async def test_missing_args_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_issues

        result = await _tool_get_issues({"projectId": "proj-001"})
        assert "error" in result

        result2 = await _tool_get_issues({"source": "backlog"})
        assert "error" in result2

    @pytest.mark.asyncio
    async def test_unknown_source_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_issues

        issue_repo = AsyncMock()
        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_issues({"projectId": "proj-001", "source": "jira"})

        assert "error" in result
        assert "jira" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_issue_list(self) -> None:
        from context_hub.mcp.server import _tool_get_issues

        issue = _make_issue()
        issue_repo = AsyncMock()
        issue_repo.find_by_project = AsyncMock(return_value=[issue])

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_issues({"projectId": "proj-001", "source": "backlog"})

        assert "error" not in result
        assert result["projectId"] == "proj-001"
        assert result["source"] == "backlog"
        issues = result["issues"]
        assert len(issues) == 1
        assert issues[0]["externalId"] == "BLG-42"
        assert issues[0]["title"] == "Fix login bug"
        assert issues[0]["status"] == "open"
        assert issues[0]["priority"] == "high"
        assert issues[0]["assignee"]["externalId"] == "user-1"
        assert issues[0]["labels"] == ["bug", "auth"]

    @pytest.mark.asyncio
    async def test_issue_without_assignee_has_null_assignee(self) -> None:
        from context_hub.mcp.server import _tool_get_issues

        issue = _make_issue(assignee=None)
        issue_repo = AsyncMock()
        issue_repo.find_by_project = AsyncMock(return_value=[issue])

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_issues({"projectId": "proj-001", "source": "backlog"})

        assert result["issues"][0]["assignee"] is None

    @pytest.mark.asyncio
    async def test_passes_status_filter_to_repo(self) -> None:
        from context_hub.mcp.server import _tool_get_issues

        issue_repo = AsyncMock()
        issue_repo.find_by_project = AsyncMock(return_value=[])

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            await _tool_get_issues(
                {"projectId": "proj-001", "source": "redmine", "status": "closed"}
            )

        call_kwargs = issue_repo.find_by_project.call_args
        assert call_kwargs is not None
        # status should be passed as IssueStatus.CLOSED
        from context_hub.shared.types import IssueStatus

        assert call_kwargs.kwargs.get("status") == IssueStatus.CLOSED or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] == IssueStatus.CLOSED
        )

    @pytest.mark.asyncio
    async def test_exception_returns_safe_error(self) -> None:
        from context_hub.mcp.server import _tool_get_issues

        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(side_effect=RuntimeError("DB down"))

        with patch.dict(sys.modules, {"context_hub.config.profiles": mock_profiles}):
            result = await _tool_get_issues({"projectId": "proj-001", "source": "backlog"})

        assert "error" in result
        assert "DB down" not in result["error"]


# ---------------------------------------------------------------------------
# get_issue_detail
# ---------------------------------------------------------------------------


class TestToolGetIssueDetail:
    """Tests for _tool_get_issue_detail."""

    @pytest.mark.asyncio
    async def test_missing_args_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_issue_detail

        result = await _tool_get_issue_detail({"projectId": "proj-001"})
        assert "error" in result

        result2 = await _tool_get_issue_detail({"issueId": "issue-001"})
        assert "error" in result2

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self) -> None:
        from context_hub.mcp.server import _tool_get_issue_detail

        issue_repo = AsyncMock()
        issue_repo.find_by_id = AsyncMock(return_value=None)

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_issue_detail(
                {"projectId": "proj-001", "issueId": "no-such-id"}
            )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_project_mismatch_returns_error(self) -> None:
        """Issue found but belonging to a different project must return 404-equivalent."""
        from context_hub.mcp.server import _tool_get_issue_detail

        issue = _make_issue(project_id="proj-other")
        issue_repo = AsyncMock()
        issue_repo.find_by_id = AsyncMock(return_value=issue)

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_issue_detail(
                {"projectId": "proj-001", "issueId": "issue-uuid-001"}
            )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_returns_issue_detail_fields_with_comments(self) -> None:
        from context_hub.mcp.server import _tool_get_issue_detail

        comment = _make_comment()
        issue = _make_issue(comments=[comment])
        issue_repo = AsyncMock()
        issue_repo.find_by_id = AsyncMock(return_value=issue)

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_issue_detail(
                {"projectId": "proj-001", "issueId": "issue-uuid-001"}
            )

        assert "error" not in result
        assert result["issueId"] == "issue-uuid-001"
        assert result["projectId"] == "proj-001"
        assert result["externalId"] == "BLG-42"
        assert result["sourceType"] == "backlog"
        assert result["title"] == "Fix login bug"
        assert result["status"] == "open"
        assert result["priority"] == "high"
        assert result["dueDate"] == "2026-06-01"
        assert result["labels"] == ["bug", "auth"]
        assert len(result["comments"]) == 1
        c = result["comments"][0]
        assert c["author"]["externalId"] == "user-2"
        assert c["author"]["name"] == "Bob"
        assert c["body"] == "Looks like a regression in the auth module."
        assert result["commentCount"] == 1

    @pytest.mark.asyncio
    async def test_issue_without_comments_returns_empty_list(self) -> None:
        from context_hub.mcp.server import _tool_get_issue_detail

        issue = _make_issue(comments=[])
        issue_repo = AsyncMock()
        issue_repo.find_by_id = AsyncMock(return_value=issue)

        with patch.dict(
            sys.modules,
            _make_module_patches(_make_settings_mock(), issue_repo=issue_repo),
        ):
            result = await _tool_get_issue_detail(
                {"projectId": "proj-001", "issueId": "issue-uuid-001"}
            )

        assert "error" not in result
        assert result["comments"] == []
        assert result["commentCount"] == 0

    @pytest.mark.asyncio
    async def test_exception_returns_safe_error(self) -> None:
        from context_hub.mcp.server import _tool_get_issue_detail

        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(side_effect=RuntimeError("DB down"))

        with patch.dict(sys.modules, {"context_hub.config.profiles": mock_profiles}):
            result = await _tool_get_issue_detail(
                {"projectId": "proj-001", "issueId": "issue-uuid-001"}
            )

        assert "error" in result
        assert "DB down" not in result["error"]


# ---------------------------------------------------------------------------
# _mcp_derive_title helper
# ---------------------------------------------------------------------------


class TestMcpDeriveTitle:
    """Tests for _mcp_derive_title."""

    def test_uses_summary_when_available(self) -> None:
        from context_hub.mcp.server import _mcp_derive_title

        doc = _make_doc_mock(summary="Sprint review summary")
        assert _mcp_derive_title(doc) == "Sprint review summary"

    def test_falls_back_to_first_line_when_no_summary(self) -> None:
        from context_hub.mcp.server import _mcp_derive_title

        doc = _make_doc_mock(text="Line one\nLine two", summary="")
        doc.structured_content.summary = ""
        assert _mcp_derive_title(doc) == "Line one"

    def test_truncates_to_80_chars(self) -> None:
        from context_hub.mcp.server import _mcp_derive_title

        doc = _make_doc_mock(summary="x" * 200)
        title = _mcp_derive_title(doc)
        assert len(title) == 80

    def test_returns_source_type_label_when_no_text(self) -> None:
        from context_hub.mcp.server import _mcp_derive_title

        doc = _make_doc_mock(text="\n\n", summary="")
        doc.structured_content.summary = ""
        doc.source_type = SourceType.MEETING
        title = _mcp_derive_title(doc)
        assert title == "[meeting]"
