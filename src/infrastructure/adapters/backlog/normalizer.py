"""Backlog → domain model normalisation.

Converts raw Backlog API dicts to Issue / Comment / Document domain objects.
Mapping rules sourced from 01-domain-model.md Section 7.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Any

from src.domain.document.entities import Document
from src.domain.issue.entities import Comment, Issue
from src.shared.types import (
    CommentId,
    IssueId,
    IssueStatus,
    IssuePriority,
    MemberRef,
    ProjectId,
    RawContent,
    SourceType,
    new_id,
)

# Backlog status name → IssueStatus
_STATUS_MAP: dict[str, IssueStatus] = {
    "未対応": IssueStatus.OPEN,
    "処理中": IssueStatus.IN_PROGRESS,
    "処理済み": IssueStatus.RESOLVED,
    "完了": IssueStatus.CLOSED,
}

# Backlog priority name → IssuePriority
_PRIORITY_MAP: dict[str, IssuePriority] = {
    "緊急": IssuePriority.URGENT,
    "高": IssuePriority.HIGH,
    "中": IssuePriority.NORMAL,
    "低": IssuePriority.LOW,
}


def normalise_issue(
    raw: dict[str, Any],
    project_id: ProjectId,
) -> Issue:
    """Convert a Backlog issue dict to an Issue domain object."""
    status_name: str = (raw.get("status") or {}).get("name", "未対応")
    priority_name: str = (raw.get("priority") or {}).get("name", "中")

    assignee_raw = raw.get("assignee")
    assignee: MemberRef | None = None
    if assignee_raw:
        assignee = MemberRef(
            external_id=str(assignee_raw.get("id", "")),
            name=assignee_raw.get("name", ""),
        )

    due_date: date | None = None
    if raw.get("dueDate"):
        try:
            due_date = datetime.fromisoformat(raw["dueDate"]).date()
        except ValueError:
            pass

    categories = [c.get("name", "") for c in (raw.get("category") or [])]
    versions = [v.get("name", "") for v in (raw.get("versions") or [])]
    labels = [l for l in (categories + versions) if l]

    created_at = _parse_iso(raw.get("created"))
    updated_at = _parse_iso(raw.get("updated"))

    return Issue.create(
        project_id=project_id,
        source_type=SourceType.BACKLOG,
        external_id=str(raw.get("id", "")),
        title=raw.get("summary", ""),
        description=raw.get("description", "") or "",
        status=_STATUS_MAP.get(status_name, IssueStatus.OPEN),
        priority=_PRIORITY_MAP.get(priority_name, IssuePriority.NORMAL),
        assignee=assignee,
        due_date=due_date,
        labels=labels,
        created_at=created_at,
        updated_at=updated_at,
    )


def normalise_comment(
    raw: dict[str, Any],
    source_type: SourceType = SourceType.BACKLOG,
) -> Comment:
    """Convert a Backlog comment dict to a Comment domain object."""
    author_raw = raw.get("createdUser") or {}
    author = MemberRef(
        external_id=str(author_raw.get("id", "")),
        name=author_raw.get("name", ""),
    )
    return Comment(
        id=CommentId(new_id()),
        source_type=source_type,
        external_id=str(raw.get("id", "")),
        author=author,
        body=raw.get("content", "") or "",
        created_at=_parse_iso(raw.get("created")),
    )


def normalise_wiki(
    raw: dict[str, Any],
    project_id: ProjectId,
    space_key: str,
) -> Document:
    """Convert a Backlog wiki page dict to a Document domain object."""
    wiki_id = raw.get("id", "")
    name = raw.get("name", "")
    content = raw.get("content", "") or ""
    project_key = (raw.get("project") or {}).get("projectKey", "")
    source_url = (
        f"https://{space_key}.backlog.com/wiki/{project_key}/{name}"
        if space_key and project_key
        else None
    )
    raw_content = RawContent(
        text=content,
        source_url=source_url,
        author_id=None,
        created_at=_parse_iso(raw.get("created")),
    )
    return Document.create(
        project_id=project_id,
        source_type=SourceType.BACKLOG,
        external_id=str(wiki_id),
        raw_content=raw_content,
    )


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.utcnow()
