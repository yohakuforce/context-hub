"""SQLite implementation of IssueRepository."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import date, datetime
from typing import Any, cast

from src.adapters.sqlite.session import open_connection
from src.domain.issue.entities import Comment, Issue
from src.domain.issue.repository import IssueRepository
from src.shared.types import (
    CommentId,
    IssueId,
    IssuePriority,
    IssueStatus,
    MemberRef,
    ProjectId,
    SourceType,
)


class SqliteIssueRepository(IssueRepository):
    """Concrete IssueRepository backed by SQLite.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def find_by_id(self, issue_id: IssueId) -> Issue | None:
        """Return the Issue with the given ID, or None.

        Args:
            issue_id: UUID string identifying the issue.

        Returns:
            Issue domain object, or None.
        """
        row = await asyncio.to_thread(self._sync_find_by_id, str(issue_id))
        return _row_to_domain(row) if row else None

    async def find_by_project(
        self,
        project_id: ProjectId,
        source_type: SourceType | None = None,
        status: IssueStatus | None = None,
        assignee_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Issue]:
        """Return issues belonging to a project with optional filters.

        Args:
            project_id:  UUID string identifying the project.
            source_type: Optional filter for source type.
            status:      Optional filter for issue status.
            assignee_id: Optional filter for assignee external ID.
            limit:       Maximum number of results.
            offset:      Pagination offset.

        Returns:
            List of Issue domain objects ordered by updated_at descending.
        """
        rows = await asyncio.to_thread(
            self._sync_find_by_project,
            str(project_id), source_type, status, assignee_id, limit, offset,
        )
        return [_row_to_domain(r) for r in rows]

    async def find_updated_since(
        self,
        project_id: ProjectId,
        source_type: SourceType,
        since: datetime,
    ) -> list[Issue]:
        """Return issues updated after *since* (for incremental sync).

        Args:
            project_id:  UUID string identifying the project.
            source_type: Source type to filter.
            since:       Datetime threshold; only issues updated after this time.

        Returns:
            List of matching Issue domain objects.
        """
        rows = await asyncio.to_thread(
            self._sync_find_updated_since,
            str(project_id), source_type.value, since.isoformat(),
        )
        return [_row_to_domain(r) for r in rows]

    async def find_by_external_id(
        self,
        project_id: ProjectId,
        source_type: SourceType,
        external_id: str,
    ) -> Issue | None:
        """Return the issue with a given external ID, or None.

        Args:
            project_id:  UUID string identifying the project.
            source_type: Source system type.
            external_id: ID in the external source system.

        Returns:
            Issue domain object, or None.
        """
        row = await asyncio.to_thread(
            self._sync_find_by_external_id,
            str(project_id), source_type.value, external_id,
        )
        return _row_to_domain(row) if row else None

    async def count_by_project(
        self,
        project_id: ProjectId,
        source_type: SourceType | None = None,
    ) -> int:
        """Return the number of issues in a project.

        Args:
            project_id:  UUID string identifying the project.
            source_type: Optional filter for a specific source type.

        Returns:
            Issue count (integer >= 0).
        """
        return await asyncio.to_thread(
            self._sync_count_by_project, str(project_id), source_type
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def save(self, issue: Issue) -> Issue:
        """Upsert an Issue (keyed on project_id + source_type + external_id).

        Args:
            issue: Issue domain object to persist.

        Returns:
            The same Issue instance (unchanged).
        """
        await asyncio.to_thread(self._sync_save, issue)
        return issue

    async def save_many(self, issues: list[Issue]) -> list[Issue]:
        """Batch upsert issues.

        Args:
            issues: List of Issue domain objects to persist.

        Returns:
            The same list of Issue instances (unchanged).
        """
        for issue in issues:
            await self.save(issue)
        return issues

    # ------------------------------------------------------------------
    # Synchronous helpers
    # ------------------------------------------------------------------

    _SELECT_COLS = (
        "id, project_id, source_type, external_id, title, description, "
        "status, priority, assignee_external_id, assignee_name, due_date, "
        "labels, comments, embedding_model, metadata, created_at, updated_at"
    )

    def _sync_find_by_id(self, issue_id: str) -> sqlite3.Row | None:
        with open_connection(self._db_path) as conn:
            return cast(
                sqlite3.Row | None,
                conn.execute(
                    f"SELECT {self._SELECT_COLS} FROM issues WHERE id = ?",  # noqa: S608
                    (issue_id,),
                ).fetchone(),
            )

    def _sync_find_by_project(
        self,
        project_id: str,
        source_type: SourceType | None,
        status: IssueStatus | None,
        assignee_id: str | None,
        limit: int,
        offset: int,
    ) -> list[sqlite3.Row]:
        with open_connection(self._db_path) as conn:
            sql = (
                f"SELECT {self._SELECT_COLS} FROM issues "  # noqa: S608
                "WHERE project_id = ? "
            )
            params: list[object] = [project_id]
            if source_type:
                sql += "AND source_type = ? "
                params.append(source_type.value)
            if status:
                sql += "AND status = ? "
                params.append(status.value)
            if assignee_id:
                sql += "AND assignee_external_id = ? "
                params.append(assignee_id)
            sql += "ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            return conn.execute(sql, params).fetchall()

    def _sync_find_updated_since(
        self, project_id: str, source_type: str, since_iso: str
    ) -> list[sqlite3.Row]:
        with open_connection(self._db_path) as conn:
            return conn.execute(
                f"SELECT {self._SELECT_COLS} FROM issues "  # noqa: S608
                "WHERE project_id = ? AND source_type = ? AND updated_at >= ?",
                (project_id, source_type, since_iso),
            ).fetchall()

    def _sync_find_by_external_id(
        self, project_id: str, source_type: str, external_id: str
    ) -> sqlite3.Row | None:
        with open_connection(self._db_path) as conn:
            return cast(
                sqlite3.Row | None,
                conn.execute(
                    f"SELECT {self._SELECT_COLS} FROM issues "  # noqa: S608
                    "WHERE project_id = ? AND source_type = ? AND external_id = ?",
                    (project_id, source_type, external_id),
                ).fetchone(),
            )

    def _sync_count_by_project(
        self, project_id: str, source_type: SourceType | None
    ) -> int:
        with open_connection(self._db_path) as conn:
            if source_type:
                row = conn.execute(
                    "SELECT COUNT(*) FROM issues "
                    "WHERE project_id = ? AND source_type = ?",
                    (project_id, source_type.value),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM issues WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
            return int(row[0]) if row else 0

    def _sync_save(self, issue: Issue) -> None:
        v = _domain_to_values(issue)
        with open_connection(self._db_path) as conn:
            conn.execute(
                "INSERT INTO issues ("
                "  id, project_id, source_type, external_id, title, description, "
                "  status, priority, assignee_external_id, assignee_name, due_date, "
                "  labels, comments, embedding_model, metadata, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id, source_type, external_id) DO UPDATE SET "
                "  title = excluded.title, "
                "  description = excluded.description, "
                "  status = excluded.status, "
                "  priority = excluded.priority, "
                "  assignee_external_id = excluded.assignee_external_id, "
                "  assignee_name = excluded.assignee_name, "
                "  due_date = excluded.due_date, "
                "  labels = excluded.labels, "
                "  comments = excluded.comments, "
                "  embedding_model = excluded.embedding_model, "
                "  metadata = excluded.metadata, "
                "  updated_at = excluded.updated_at",
                (
                    v["id"], v["project_id"], v["source_type"], v["external_id"],
                    v["title"], v["description"], v["status"], v["priority"],
                    v["assignee_external_id"], v["assignee_name"], v["due_date"],
                    v["labels"], v["comments"], v["embedding_model"],
                    v["metadata"], v["created_at"], v["updated_at"],
                ),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _domain_to_values(issue: Issue) -> dict[str, Any]:
    embedding_model = issue.embedding_vector.model_name if issue.embedding_vector else None
    comments_json = json.dumps(
        [
            {
                "id": str(c.id),
                "source_type": c.source_type.value,
                "external_id": c.external_id,
                "author_external_id": c.author.external_id,
                "author_name": c.author.name,
                "body": c.body,
                "created_at": c.created_at.isoformat(),
            }
            for c in issue.comments
        ]
    )
    return {
        "id": str(issue.id),
        "project_id": str(issue.project_id),
        "source_type": issue.source_type.value,
        "external_id": issue.external_id,
        "title": issue.title,
        "description": issue.description,
        "status": issue.status.value,
        "priority": issue.priority.value,
        "assignee_external_id": issue.assignee.external_id if issue.assignee else None,
        "assignee_name": issue.assignee.name if issue.assignee else None,
        "due_date": issue.due_date.isoformat() if issue.due_date else None,
        "labels": json.dumps(issue.labels),
        "comments": comments_json,
        "embedding_model": embedding_model,
        "metadata": "{}",
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
    }


def _row_to_domain(row: sqlite3.Row) -> Issue:
    (
        issue_id, project_id, source_type, external_id, title, description,
        status, priority, assignee_ext_id, assignee_name, due_date_str,
        labels_json, comments_json, embedding_model, metadata_json,
        created_at, updated_at,
    ) = row

    assignee = None
    if assignee_ext_id:
        assignee = MemberRef(external_id=assignee_ext_id, name=assignee_name or "")

    due_date: date | None = None
    if due_date_str:
        due_date = date.fromisoformat(due_date_str)

    comments_raw: list[dict[str, Any]] = json.loads(comments_json or "[]")
    comments = [
        Comment(
            id=CommentId(c["id"]),
            source_type=SourceType(c["source_type"]),
            external_id=c["external_id"],
            author=MemberRef(
                external_id=c["author_external_id"],
                name=c["author_name"],
            ),
            body=c["body"],
            created_at=datetime.fromisoformat(c["created_at"]),
        )
        for c in comments_raw
    ]

    return Issue(
        id=IssueId(issue_id),
        project_id=ProjectId(project_id),
        source_type=SourceType(source_type),
        external_id=external_id,
        title=title,
        description=description,
        status=IssueStatus(status),
        priority=IssuePriority(priority),
        assignee=assignee,
        due_date=due_date,
        comments=comments,
        labels=json.loads(labels_json or "[]"),
        embedding_vector=None,
        created_at=datetime.fromisoformat(created_at),
        updated_at=datetime.fromisoformat(updated_at),
    )
