"""PostgreSQL + pgvector implementation of IssueRepository."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from context_hub.domain.issue.entities import Comment, Issue
from context_hub.domain.issue.repository import IssueRepository
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


class PostgresIssueRepository(IssueRepository):
    """Concrete Issue repository backed by PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def find_by_id(self, issue_id: IssueId) -> Optional[Issue]:
        row = await self._session.get(IssueRow, str(issue_id))
        return _row_to_domain(row) if row else None

    async def find_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
        status: Optional[IssueStatus] = None,
        assignee_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Issue]:
        q = (
            select(IssueRow)
            .where(IssueRow.project_id == str(project_id))
            .order_by(IssueRow.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if source_type:
            q = q.where(IssueRow.source_type == source_type.value)
        if status:
            q = q.where(IssueRow.status == status.value)
        if assignee_id:
            q = q.where(IssueRow.assignee_external_id == assignee_id)
        result = await self._session.execute(q)
        return [_row_to_domain(r) for r in result.scalars().all()]

    async def find_updated_since(
        self,
        project_id: ProjectId,
        source_type: SourceType,
        since: datetime,
    ) -> list[Issue]:
        result = await self._session.execute(
            select(IssueRow).where(
                IssueRow.project_id == str(project_id),
                IssueRow.source_type == source_type.value,
                IssueRow.updated_at >= since,
            )
        )
        return [_row_to_domain(r) for r in result.scalars().all()]

    async def find_by_external_id(
        self,
        project_id: ProjectId,
        source_type: SourceType,
        external_id: str,
    ) -> Optional[Issue]:
        result = await self._session.execute(
            select(IssueRow).where(
                IssueRow.project_id == str(project_id),
                IssueRow.source_type == source_type.value,
                IssueRow.external_id == external_id,
            )
        )
        row = result.scalar_one_or_none()
        return _row_to_domain(row) if row else None

    async def count_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
    ) -> int:
        q = select(func.count()).where(IssueRow.project_id == str(project_id))
        if source_type:
            q = q.where(IssueRow.source_type == source_type.value)
        result = await self._session.execute(q)
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def save(self, issue: Issue) -> Issue:
        values = _domain_to_values(issue)
        stmt = (
            pg_insert(IssueRow)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["project_id", "source_type", "external_id"],
                set_={
                    "title": values["title"],
                    "description": values["description"],
                    "status": values["status"],
                    "priority": values["priority"],
                    "assignee_external_id": values["assignee_external_id"],
                    "assignee_name": values["assignee_name"],
                    "due_date": values["due_date"],
                    "labels": values["labels"],
                    "comments": values["comments"],
                    "embedding": values["embedding"],
                    "embedding_model": values["embedding_model"],
                    "metadata_": values["metadata_"],
                    "updated_at": values["updated_at"],
                },
            )
        )
        await self._session.execute(stmt)
        return issue

    async def save_many(self, issues: list[Issue]) -> list[Issue]:
        """Batch upsert — executes individual saves in a single transaction."""
        for issue in issues:
            await self.save(issue)
        return issues


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _domain_to_values(issue: Issue) -> dict:
    embedding_val = None
    embedding_model = None
    if issue.embedding_vector:
        embedding_val = list(issue.embedding_vector.values)
        embedding_model = issue.embedding_vector.model_name

    comments_json = [
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
        "labels": issue.labels,
        "comments": comments_json,
        "embedding": embedding_val,
        "embedding_model": embedding_model,
        "metadata_": {},
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
    }


def _row_to_domain(row: IssueRow) -> Issue:
    assignee = None
    if row.assignee_external_id:
        assignee = MemberRef(
            external_id=row.assignee_external_id,
            name=row.assignee_name or "",
        )

    due_date: Optional[date] = None
    if row.due_date:
        due_date = date.fromisoformat(row.due_date)

    comments_raw = row.comments or []
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

    embedding = None
    if row.embedding is not None:
        vec_values = tuple(float(v) for v in row.embedding)
        embedding = EmbeddingVector(
            values=vec_values,
            model_name=row.embedding_model or "unknown",
            dimensions=len(vec_values),
        )

    return Issue(
        id=IssueId(row.id),
        project_id=ProjectId(row.project_id),
        source_type=SourceType(row.source_type),
        external_id=row.external_id,
        title=row.title,
        description=row.description,
        status=IssueStatus(row.status),
        priority=IssuePriority(row.priority),
        assignee=assignee,
        due_date=due_date,
        comments=comments,
        labels=list(row.labels or []),
        embedding_vector=embedding,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
