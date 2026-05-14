"""Unit tests for Redmine normalizer."""

from src.infrastructure.adapters.redmine.normalizer import (
    normalise_issue,
    normalise_journal,
    normalise_wiki,
)
from src.shared.types import IssueStatus, IssuePriority, ProjectId, SourceType, new_id


def _project_id() -> ProjectId:
    return ProjectId(new_id())


class TestNormaliseIssue:
    def _raw_issue(self) -> dict:
        return {
            "id": 55,
            "subject": "Server error on login",
            "description": "500 error appears on POST /login",
            "status": {"id": 2, "name": "In Progress"},
            "priority": {"id": 2, "name": "High"},
            "assigned_to": {"id": 7, "name": "Yamada"},
            "due_date": "2026-05-25",
            "tracker": {"name": "Bug"},
            "category": {"name": "API"},
            "created_on": "2026-05-10T09:00:00Z",
            "updated_on": "2026-05-13T17:00:00Z",
            "journals": [],
        }

    def test_maps_id_as_string(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.external_id == "55"

    def test_maps_title_from_subject(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.title == "Server error on login"

    def test_maps_status_in_progress(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.status == IssueStatus.IN_PROGRESS

    def test_maps_priority_high(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.priority == IssuePriority.HIGH

    def test_maps_assignee(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.assignee is not None
        assert issue.assignee.name == "Yamada"

    def test_source_type_is_redmine(self):
        issue = normalise_issue(self._raw_issue(), _project_id())
        assert issue.source_type == SourceType.REDMINE

    def test_journals_with_notes_become_comments(self):
        raw = self._raw_issue()
        raw["journals"] = [
            {
                "id": 1,
                "user": {"id": 7, "name": "Yamada"},
                "notes": "Fixed in branch feature/x",
                "created_on": "2026-05-13T17:00:00Z",
            },
            {
                "id": 2,
                "user": {"id": 7, "name": "Yamada"},
                "notes": "",  # activity-only, no notes — should be skipped
                "created_on": "2026-05-13T17:01:00Z",
            },
        ]
        issue = normalise_issue(raw, _project_id())
        assert len(issue.comments) == 1
        assert issue.comments[0].body == "Fixed in branch feature/x"
