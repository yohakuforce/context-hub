"""Unit tests for Backlog normalizer."""

from datetime import datetime

import pytest

from src.infrastructure.adapters.backlog.normalizer import (
    normalise_comment,
    normalise_issue,
    normalise_wiki,
)
from src.shared.types import IssueStatus, IssuePriority, ProjectId, SourceType, new_id


def _project_id() -> ProjectId:
    return ProjectId(new_id())


class TestNormaliseIssue:
    def _raw_issue(self) -> dict:
        return {
            "id": 42,
            "summary": "Fix login bug",
            "description": "Login fails on Safari.",
            "status": {"id": 2, "name": "処理中"},
            "priority": {"id": 3, "name": "高"},
            "assignee": {"id": 100, "name": "田中 太郎"},
            "dueDate": "2026-05-20T00:00:00Z",
            "category": [{"name": "フロントエンド"}],
            "versions": [{"name": "v1.0"}],
            "created": "2026-05-10T09:00:00Z",
            "updated": "2026-05-13T18:00:00Z",
        }

    def test_maps_id_as_string(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.external_id == "42"

    def test_maps_title(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.title == "Fix login bug"

    def test_maps_status_in_progress(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.status == IssueStatus.IN_PROGRESS

    def test_maps_priority_high(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.priority == IssuePriority.HIGH

    def test_maps_assignee(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.assignee is not None
        assert issue.assignee.external_id == "100"
        assert issue.assignee.name == "田中 太郎"

    def test_maps_due_date(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.due_date is not None
        assert issue.due_date.year == 2026

    def test_maps_labels_from_category_and_versions(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert "フロントエンド" in issue.labels
        assert "v1.0" in issue.labels

    def test_source_type_is_backlog(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.source_type == SourceType.BACKLOG

    def test_unknown_status_defaults_to_open(self):
        raw = self._raw_issue()
        raw["status"] = {"name": "UnknownStatus"}
        issue = normalise_issue(raw, _project_id())
        assert issue.status == IssueStatus.OPEN

    def test_no_assignee(self):
        raw = self._raw_issue()
        raw["assignee"] = None
        issue = normalise_issue(raw, _project_id())
        assert issue.assignee is None


class TestNormaliseComment:
    def test_maps_comment_fields(self):
        raw = {
            "id": 999,
            "content": "LGTM",
            "createdUser": {"id": 200, "name": "鈴木 花子"},
            "created": "2026-05-13T15:00:00Z",
        }
        comment = normalise_comment(raw)
        assert comment.external_id == "999"
        assert comment.body == "LGTM"
        assert comment.author.name == "鈴木 花子"
        assert comment.source_type == SourceType.BACKLOG
