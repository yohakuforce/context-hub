"""Initial schema — all tables, indexes, triggers, pgvector extension.

Revision ID: 0001
Revises: (none)
Create Date: 2026-05-15

Tables:
  - projects
  - documents    (HNSW on embedding, GIN on content_tsv, GIN on metadata JSONB)
  - issues       (HNSW on embedding, GIN on content_tsv, GIN on metadata JSONB)
  - ingestion_jobs
  - consumers
  - permissions
  - audit_logs

pgvector notes:
  - Extension is enabled via CREATE EXTENSION IF NOT EXISTS vector
  - HNSW index uses m=16, ef_construction=64 (balanced precision/speed)
  - cosine distance operator: vector_cosine_ops
  - 1024 dimensions = BGE-M3 dense output

tsvector trigger:
  - documents.content_tsv is maintained by a BEFORE INSERT OR UPDATE trigger
    that concatenates raw_text + COALESCE(summary, '')
  - issues.content_tsv is maintained similarly: title || ' ' || description
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 0. Enable pgvector extension
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # 1. projects
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("external_project_id", sa.String(255), nullable=True),
        sa.Column("sources", JSONB, nullable=False, server_default="'[]'"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_projects_external_project_id",
        "projects",
        ["external_project_id"],
    )

    # ------------------------------------------------------------------
    # 2. ingestion_jobs (before documents due to FK)
    # ------------------------------------------------------------------
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("sync_cursor_source_type", sa.String(32), nullable=True),
        sa.Column("sync_cursor_value", sa.Text, nullable=True),
        sa.Column("items_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors", JSONB, nullable=False, server_default="'[]'"),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_ingestion_jobs_project_id", "ingestion_jobs", ["project_id"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])

    # ------------------------------------------------------------------
    # 3. documents
    # ------------------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("author_id", sa.String(255), nullable=True),
        sa.Column("raw_created_at", sa.DateTime, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("entities", JSONB, nullable=True),
        # pgvector column — 1024 dims for BGE-M3
        sa.Column("embedding", sa.Text, nullable=True),   # placeholder; replaced below
        sa.Column("embedding_model", sa.String(128), nullable=True),
        sa.Column("content_tsv", TSVECTOR, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="'{}'"),
        sa.Column(
            "ingestion_job_id",
            sa.String(36),
            sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    # Replace placeholder Text column with real pgvector type
    op.execute("ALTER TABLE documents DROP COLUMN embedding")
    op.execute("ALTER TABLE documents ADD COLUMN embedding vector(1024)")

    op.create_index(
        "uq_document_source",
        "documents",
        ["project_id", "source_type", "external_id"],
        unique=True,
    )
    op.create_index("ix_documents_project_id", "documents", ["project_id"])
    op.create_index("ix_documents_ingestion_job_id", "documents", ["ingestion_job_id"])

    # GIN index for full-text search
    op.execute(
        "CREATE INDEX ix_documents_content_tsv ON documents USING gin (content_tsv)"
    )
    # GIN index for JSONB metadata filters
    op.execute(
        "CREATE INDEX ix_documents_metadata ON documents USING gin "
        "(metadata jsonb_path_ops)"
    )
    # HNSW index for vector similarity (cosine distance)
    op.execute(
        "CREATE INDEX ix_documents_embedding_hnsw ON documents "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # tsvector auto-update trigger for documents
    op.execute(
        """
        CREATE OR REPLACE FUNCTION documents_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.content_tsv :=
                to_tsvector('simple',
                    COALESCE(NEW.raw_text, '') || ' ' ||
                    COALESCE(NEW.summary, '')
                );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_documents_tsv
        BEFORE INSERT OR UPDATE OF raw_text, summary
        ON documents
        FOR EACH ROW EXECUTE FUNCTION documents_tsv_update();
        """
    )

    # ------------------------------------------------------------------
    # 4. issues
    # ------------------------------------------------------------------
    op.create_table(
        "issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default="''"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("assignee_external_id", sa.String(255), nullable=True),
        sa.Column("assignee_name", sa.String(255), nullable=True),
        sa.Column("due_date", sa.String(16), nullable=True),
        sa.Column("labels", JSONB, nullable=False, server_default="'[]'"),
        sa.Column("comments", JSONB, nullable=False, server_default="'[]'"),
        sa.Column("embedding", sa.Text, nullable=True),   # placeholder
        sa.Column("embedding_model", sa.String(128), nullable=True),
        sa.Column("content_tsv", TSVECTOR, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.execute("ALTER TABLE issues DROP COLUMN embedding")
    op.execute("ALTER TABLE issues ADD COLUMN embedding vector(1024)")

    op.create_index(
        "uq_issue_source",
        "issues",
        ["project_id", "source_type", "external_id"],
        unique=True,
    )
    op.create_index("ix_issues_project_id", "issues", ["project_id"])
    op.execute(
        "CREATE INDEX ix_issues_content_tsv ON issues USING gin (content_tsv)"
    )
    op.execute(
        "CREATE INDEX ix_issues_metadata ON issues USING gin "
        "(metadata jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX ix_issues_embedding_hnsw ON issues "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION issues_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.content_tsv :=
                to_tsvector('simple',
                    COALESCE(NEW.title, '') || ' ' ||
                    COALESCE(NEW.description, '')
                );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_issues_tsv
        BEFORE INSERT OR UPDATE OF title, description
        ON issues
        FOR EACH ROW EXECUTE FUNCTION issues_tsv_update();
        """
    )

    # ------------------------------------------------------------------
    # 5. consumers
    # ------------------------------------------------------------------
    op.create_table(
        "consumers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("api_key_hash", sa.String(512), nullable=False),
        sa.Column(
            "api_key_algorithm",
            sa.String(32),
            nullable=False,
            server_default="'bcrypt'",
        ),
        sa.Column("api_key_created_at", sa.DateTime, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # ------------------------------------------------------------------
    # 6. permissions
    # ------------------------------------------------------------------
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "consumer_id",
            sa.String(36),
            sa.ForeignKey("consumers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("scopes", JSONB, nullable=False, server_default="'[]'"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_permissions_consumer_id", "permissions", ["consumer_id"])
    op.create_index("ix_permissions_project_id", "permissions", ["project_id"])

    # ------------------------------------------------------------------
    # 7. audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("operation_type", sa.String(64), nullable=False),
        sa.Column("consumer_id", sa.String(36), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("resource_id", sa.String(512), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_audit_logs_operation_type", "audit_logs", ["operation_type"])
    op.create_index("ix_audit_logs_consumer_id", "audit_logs", ["consumer_id"])
    op.create_index("ix_audit_logs_project_id", "audit_logs", ["project_id"])
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.execute("DROP TRIGGER IF EXISTS trg_issues_tsv ON issues")
    op.execute("DROP FUNCTION IF EXISTS issues_tsv_update()")
    op.execute("DROP TRIGGER IF EXISTS trg_documents_tsv ON documents")
    op.execute("DROP FUNCTION IF EXISTS documents_tsv_update()")

    op.drop_table("audit_logs")
    op.drop_table("permissions")
    op.drop_table("consumers")
    op.drop_table("issues")
    op.drop_table("documents")
    op.drop_table("ingestion_jobs")
    op.drop_table("projects")
