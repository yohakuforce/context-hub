"""Redmine → domain model normalisation.

Mapping rules sourced from 01-domain-model.md Section 7.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.domain.document.entities import Document
from src.domain.issue.entities import Comment, Issue
from src.shared.types import (
    CommentId,
    IssueStatus,
    IssuePriority,
    MemberRef,
    ProjectId,
    RawContent,
    SourceType,
    new_id,
)

_STATUS_MAP: dict[str, IssueStatus] = {
    "New": IssueStatus.OPEN,
    "In Progress": IssueStatus.IN_PROGRESS,
    "Resolved": IssueStatus.RESOLVED,
    "Closed": IssueStatus.CLOSED,
    "Feedback": IssueStatus.IN_PROGRESS,  # best-effort normalisation
    "Rejected": IssueStatus.CLOSED,
}

_PRIORITY_MAP: dict[str, IssuePriority] = {
    "Immediate": IssuePriority.URGENT,
    "Urgent": IssuePriority.URGENT,
    "High": IssuePriority.HIGH,
    "Normal": IssuePriority.NORMAL,
    "Low": IssuePriority.LOW,
}


def normalise_issue(
    raw: dict[str, Any],
    project_id: ProjectId,
) -> Issue:
    status_name: str = (raw.get("status") or {}).get("name", "New")
    priority_name: str = (raw.get("priority") or {}).get("name", "Normal")

    assignee_raw = raw.get("assigned_to")
    assignee: MemberRef | None = None
    if assignee_raw:
        assignee = MemberRef(
            external_id=str(assignee_raw.get("id", "")),
            name=assignee_raw.get("name", ""),
        )

    due_date: date | None = None
    if raw.get("due_date"):
        try:
            due_date = date.fromisoformat(raw["due_date"])
        except ValueError:
            pass

    tracker_name = (raw.get("tracker") or {}).get("name", "")
    category_name = (raw.get("category") or {}).get("name", "")
    labels = [l for l in [tracker_name, category_name] if l]

    issue = Issue.create(
        project_id=project_id,
        source_type=SourceType.REDMINE,
        external_id=str(raw.get("id", "")),
        title=raw.get("subject", ""),
        description=raw.get("description", "") or "",
        status=_STATUS_MAP.get(status_name, IssueStatus.OPEN),
        priority=_PRIORITY_MAP.get(priority_name, IssuePriority.NORMAL),
        assignee=assignee,
        due_date=due_date,
        labels=labels,
        created_at=_parse_iso(raw.get("created_on")),
        updated_at=_parse_iso(raw.get("updated_on")),
    )

    # Attach journals as comments
    journals: list[dict[str, Any]] = raw.get("journals", [])
    comments = [
        normalise_journal(j)
        for j in journals
        if j.get("notes")  # skip activity-only entries with no comment text
    ]
    if comments:
        issue = issue.with_comments(comments)

    return issue


def normalise_journal(raw: dict[str, Any]) -> Comment:
    user_raw = raw.get("user") or {}
    author = MemberRef(
        external_id=str(user_raw.get("id", "")),
        name=user_raw.get("name", ""),
    )
    return Comment(
        id=CommentId(new_id()),
        source_type=SourceType.REDMINE,
        external_id=str(raw.get("id", "")),
        author=author,
        body=raw.get("notes", "") or "",
        created_at=_parse_iso(raw.get("created_on")),
    )


def normalise_wiki(
    raw: dict[str, Any],
    project_id: ProjectId,
    base_url: str,
    project_identifier: str,
) -> Document:
    title = raw.get("title", "")
    text = raw.get("text", "") or ""
    source_url = (
        f"{base_url.rstrip('/')}/projects/{project_identifier}/wiki/{title}"
        if base_url and project_identifier
        else None
    )
    raw_content = RawContent(
        text=text,
        source_url=source_url,
        author_id=None,
        created_at=_parse_iso(raw.get("created_on")),
    )
    return Document.create(
        project_id=project_id,
        source_type=SourceType.REDMINE,
        external_id=title,  # Redmine wiki uses title as identifier
        raw_content=raw_content,
    )


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.utcnow()
