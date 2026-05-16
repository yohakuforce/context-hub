"""Issue aggregate root and Comment entity.

Issue represents a normalised ticket/issue from Backlog or Redmine.
Comment is an entity within the Issue aggregate (Slack message thread reply,
Backlog comment, or Redmine journal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from context_hub.shared.types import (
    CommentId,
    EmbeddingVector,
    IssueId,
    IssueStatus,
    IssuePriority,
    MemberRef,
    ProjectId,
    SourceType,
    new_id,
)


@dataclass(frozen=True)
class Comment:
    """A single comment/journal entry associated with an Issue.

    Immutable — each normalised comment is created once and not mutated.
    Source: Slack reply thread, Backlog comment, or Redmine journal.
    """

    id: CommentId
    source_type: SourceType
    external_id: str
    author: MemberRef
    body: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        source_type: SourceType,
        external_id: str,
        author: MemberRef,
        body: str,
        created_at: datetime,
    ) -> "Comment":
        return cls(
            id=CommentId(new_id()),
            source_type=source_type,
            external_id=external_id,
            author=author,
            body=body,
            created_at=created_at,
        )


@dataclass
class Issue:
    """Aggregate root for a normalised Backlog/Redmine ticket.

    Kept separate from Document because issues have richer structured metadata
    (status, priority, assignee, due date) and a different sync lifecycle.
    """

    id: IssueId
    project_id: ProjectId
    source_type: SourceType           # BACKLOG or REDMINE
    external_id: str                  # Backlog issue ID or Redmine issue ID (stringified)
    title: str
    description: str
    status: IssueStatus
    priority: IssuePriority
    assignee: Optional[MemberRef]
    due_date: Optional[date]
    comments: list[Comment]
    labels: list[str]
    embedding_vector: Optional[EmbeddingVector]
    created_at: datetime
    updated_at: datetime

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        project_id: ProjectId,
        source_type: SourceType,
        external_id: str,
        title: str,
        description: str,
        status: IssueStatus,
        priority: IssuePriority,
        assignee: Optional[MemberRef] = None,
        due_date: Optional[date] = None,
        labels: Optional[list[str]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> "Issue":
        now = datetime.utcnow()
        return cls(
            id=IssueId(new_id()),
            project_id=project_id,
            source_type=source_type,
            external_id=external_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assignee=assignee,
            due_date=due_date,
            comments=[],
            labels=labels or [],
            embedding_vector=None,
            created_at=created_at or now,
            updated_at=updated_at or now,
        )

    # ------------------------------------------------------------------
    # Domain behaviour
    # ------------------------------------------------------------------

    def with_comments(self, comments: list[Comment]) -> "Issue":
        """Return a new Issue with the comment list replaced."""
        return Issue(
            id=self.id,
            project_id=self.project_id,
            source_type=self.source_type,
            external_id=self.external_id,
            title=self.title,
            description=self.description,
            status=self.status,
            priority=self.priority,
            assignee=self.assignee,
            due_date=self.due_date,
            comments=list(comments),
            labels=list(self.labels),
            embedding_vector=self.embedding_vector,
            created_at=self.created_at,
            updated_at=datetime.utcnow(),
        )

    def with_embedding(self, vector: EmbeddingVector) -> "Issue":
        """Return a new Issue with the embedding vector attached."""
        return Issue(
            id=self.id,
            project_id=self.project_id,
            source_type=self.source_type,
            external_id=self.external_id,
            title=self.title,
            description=self.description,
            status=self.status,
            priority=self.priority,
            assignee=self.assignee,
            due_date=self.due_date,
            comments=list(self.comments),
            labels=list(self.labels),
            embedding_vector=vector,
            created_at=self.created_at,
            updated_at=datetime.utcnow(),
        )

    @property
    def is_open(self) -> bool:
        return self.status in (IssueStatus.OPEN, IssueStatus.IN_PROGRESS)
