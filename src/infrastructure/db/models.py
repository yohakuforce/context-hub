"""SQLAlchemy ORM models for Context-Hub.

All domain aggregates map to tables defined here.
pgvector columns use 1024 dimensions (BGE-M3).
HNSW index + GIN index for tsvector/JSONB are declared as Index objects
and emitted by Alembic in the initial migration.

Column decisions:
  - embedding: pgvector vector(1024) — BGE-M3 dense output
  - content_tsv: tsvector — maintained by a BEFORE INSERT/UPDATE trigger in migration
  - metadata_: JSONB — open-ended extra context per document/issue
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectRow(Base):
    """ORM representation of the Project aggregate root."""

    __tablename__ = "projects"

    id = Column(UUID(as_uuid=False), primary_key=True)
    name = Column(String(255), nullable=False)
    external_project_id = Column(String(255), nullable=True, index=True)
    # SourceConfig list is stored as JSONB array (avoids a separate table for PoC scale)
    sources = Column(JSONB, nullable=False, server_default="'[]'")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    documents = relationship(
        "DocumentRow", back_populates="project", cascade="all, delete-orphan"
    )
    issues = relationship(
        "IssueRow", back_populates="project", cascade="all, delete-orphan"
    )
    ingestion_jobs = relationship(
        "IngestionJobRow", back_populates="project", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentRow(Base):
    """ORM representation of the Document aggregate root.

    content_tsv is populated by a DB trigger defined in the initial migration.
    The trigger recomputes the column on every INSERT / UPDATE of raw_text.
    """

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=False), primary_key=True)
    project_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type = Column(String(32), nullable=False)
    external_id = Column(String(512), nullable=False)
    raw_text = Column(Text, nullable=False)
    source_url = Column(Text, nullable=True)
    author_id = Column(String(255), nullable=True)
    raw_created_at = Column(DateTime, nullable=True)

    # LLM-structured output (nullable until processing is done)
    summary = Column(Text, nullable=True)
    language = Column(String(16), nullable=True)
    tags = Column(JSONB, nullable=True)          # list[str]
    entities = Column(JSONB, nullable=True)      # list[{name, entity_type}]

    # Embedding — 1024 dimensions for BGE-M3
    embedding = Column(Vector(1024), nullable=True)
    embedding_model = Column(String(128), nullable=True)

    # Full-text search vector (maintained by DB trigger in migration)
    content_tsv = Column(TSVECTOR, nullable=True)

    # Open-ended metadata for filters (source-specific fields, ingestion job ref, etc.)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="'{}'")

    ingestion_job_id = Column(
        UUID(as_uuid=False),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("ProjectRow", back_populates="documents")
    ingestion_job = relationship("IngestionJobRow", back_populates="documents")

    __table_args__ = (
        # Unique constraint for upsert deduplication
        Index(
            "uq_document_source",
            "project_id",
            "source_type",
            "external_id",
            unique=True,
        ),
        # HNSW index for vector similarity search (cosine)
        # DDL emitted as raw SQL in the Alembic migration (pgvector syntax)
        # GIN index for full-text search
        Index("ix_documents_content_tsv", "content_tsv", postgresql_using="gin"),
        # GIN index for JSONB metadata filters
        Index(
            "ix_documents_metadata",
            "metadata",
            postgresql_using="gin",
            postgresql_ops={"metadata": "jsonb_path_ops"},
        ),
    )


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


class IssueRow(Base):
    """ORM representation of the Issue aggregate root."""

    __tablename__ = "issues"

    id = Column(UUID(as_uuid=False), primary_key=True)
    project_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type = Column(String(32), nullable=False)
    external_id = Column(String(512), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False, server_default="''")
    status = Column(String(32), nullable=False)
    priority = Column(String(32), nullable=False)
    assignee_external_id = Column(String(255), nullable=True)
    assignee_name = Column(String(255), nullable=True)
    due_date = Column(String(16), nullable=True)   # ISO date string
    labels = Column(JSONB, nullable=False, server_default="'[]'")
    comments = Column(JSONB, nullable=False, server_default="'[]'")

    # Embedding — 1024 dimensions for BGE-M3
    embedding = Column(Vector(1024), nullable=True)
    embedding_model = Column(String(128), nullable=True)

    # Full-text search vector (trigger-maintained)
    content_tsv = Column(TSVECTOR, nullable=True)

    metadata_ = Column("metadata", JSONB, nullable=False, server_default="'{}'")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("ProjectRow", back_populates="issues")

    __table_args__ = (
        Index(
            "uq_issue_source",
            "project_id",
            "source_type",
            "external_id",
            unique=True,
        ),
        Index("ix_issues_content_tsv", "content_tsv", postgresql_using="gin"),
        Index(
            "ix_issues_metadata",
            "metadata",
            postgresql_using="gin",
            postgresql_ops={"metadata": "jsonb_path_ops"},
        ),
    )


# ---------------------------------------------------------------------------
# IngestionJobs
# ---------------------------------------------------------------------------


class IngestionJobRow(Base):
    """ORM representation of the IngestionJob aggregate root."""

    __tablename__ = "ingestion_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True)
    project_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    sync_cursor_source_type = Column(String(32), nullable=True)
    sync_cursor_value = Column(Text, nullable=True)
    items_processed = Column(Integer, nullable=False, default=0)
    errors = Column(JSONB, nullable=False, server_default="'[]'")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("ProjectRow", back_populates="ingestion_jobs")
    documents = relationship("DocumentRow", back_populates="ingestion_job")


# ---------------------------------------------------------------------------
# Access Control
# ---------------------------------------------------------------------------


class ConsumerRow(Base):
    """ORM representation of the Consumer aggregate (API key holder)."""

    __tablename__ = "consumers"

    id = Column(UUID(as_uuid=False), primary_key=True)
    name = Column(String(255), nullable=False)
    api_key_hash = Column(String(512), nullable=False)
    api_key_algorithm = Column(String(32), nullable=False, server_default="'bcrypt'")
    api_key_created_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    permissions = relationship(
        "PermissionRow", back_populates="consumer", cascade="all, delete-orphan"
    )


class PermissionRow(Base):
    """ORM representation of a Permission grant."""

    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=False), primary_key=True)
    consumer_id = Column(
        UUID(as_uuid=False),
        ForeignKey("consumers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(
        UUID(as_uuid=False),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    scopes = Column(JSONB, nullable=False, server_default="'[]'")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    consumer = relationship("ConsumerRow", back_populates="permissions")


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


class AuditLogRow(Base):
    """ORM representation of the AuditLog entry (append-only)."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=False), primary_key=True)
    operation_type = Column(String(64), nullable=False, index=True)
    consumer_id = Column(UUID(as_uuid=False), nullable=True, index=True)
    project_id = Column(UUID(as_uuid=False), nullable=True, index=True)
    resource_id = Column(String(512), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="'{}'")
    occurred_at = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_audit_logs_occurred_at", "occurred_at"),
    )
