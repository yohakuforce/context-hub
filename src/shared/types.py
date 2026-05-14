"""Shared value objects and type definitions used across all bounded contexts.

All value objects here are immutable (frozen dataclasses or simple NewType wrappers).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import NewType

# ---------------------------------------------------------------------------
# Strongly-typed IDs (NewType wrappers around UUID strings)
# ---------------------------------------------------------------------------

ProjectId = NewType("ProjectId", str)
DocumentId = NewType("DocumentId", str)
IssueId = NewType("IssueId", str)
CommentId = NewType("CommentId", str)
IngestionJobId = NewType("IngestionJobId", str)
PermissionId = NewType("PermissionId", str)
ConsumerId = NewType("ConsumerId", str)
AuditLogId = NewType("AuditLogId", str)


def new_id() -> str:
    """Generate a new UUID v4 string."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SourceType(str, Enum):
    """Identifies the origin system of a Document or Issue."""

    SLACK = "slack"
    BACKLOG = "backlog"
    REDMINE = "redmine"
    MEETING = "meeting"
    FILE = "file"
    EMAIL = "email"


class IssueStatus(str, Enum):
    """Normalised issue/ticket status (maps Backlog & Redmine statuses)."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IssuePriority(str, Enum):
    """Normalised issue priority."""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class JobStatus(str, Enum):
    """Lifecycle status of an IngestionJob."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Scope(str, Enum):
    """Permission scope for Consumer access control."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class EntityType(str, Enum):
    """Semantic type of an extracted Entity."""

    PERSON = "person"
    PROJECT = "project"
    CUSTOMER = "customer"
    TASK = "task"
    TERM = "term"


# ---------------------------------------------------------------------------
# Immutable value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawContent:
    """Immutable raw content captured from a Source.

    Never modified after creation — represents the original source text.
    """

    text: str
    source_url: str | None
    author_id: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("RawContent.text must not be empty")


@dataclass(frozen=True)
class StructuredContent:
    """Result of LLM-based structuring of a Document.

    Mutable in the sense that a Document can be re-structured, but each
    StructuredContent instance is itself immutable — updates produce a new
    instance.
    """

    summary: str
    language: str
    tags: tuple[str, ...]
    entities: tuple["ExtractedEntity", ...]


@dataclass(frozen=True)
class ExtractedEntity:
    """An entity extracted from a Document by the LLM."""

    name: str
    entity_type: EntityType


@dataclass(frozen=True)
class EmbeddingVector:
    """Immutable embedding vector with provenance metadata."""

    values: tuple[float, ...]
    model_name: str
    dimensions: int

    def __post_init__(self) -> None:
        if len(self.values) != self.dimensions:
            raise ValueError(
                f"EmbeddingVector dimensions mismatch: "
                f"expected {self.dimensions}, got {len(self.values)}"
            )


@dataclass(frozen=True)
class SyncCursor:
    """Immutable pointer tracking incremental-sync progress per Source."""

    source_type: SourceType
    cursor_value: str  # ISO-8601 timestamp or Slack pagination token


@dataclass(frozen=True)
class MemberRef:
    """Lightweight reference to an external team member."""

    external_id: str
    name: str


@dataclass(frozen=True)
class SyncError:
    """Records a single item-level error inside an IngestionJob."""

    item_id: str
    message: str
    occurred_at: datetime
