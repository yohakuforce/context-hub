"""PostgreSQL / pgvector adapter package.

Re-exports all Postgres repository implementations so that the rest of the
codebase can import from a single, stable location.
"""

from context_hub.adapters.postgres.document_repository import PostgresDocumentRepository
from context_hub.adapters.postgres.project_repository import PostgresProjectRepository
from context_hub.adapters.postgres.issue_repository import PostgresIssueRepository
from context_hub.adapters.postgres.ingestion_job_repository import PostgresIngestionJobRepository
from context_hub.adapters.postgres.access_control_repository import (
    PostgresConsumerRepository,
    PostgresPermissionRepository,
)
from context_hub.adapters.postgres.audit_log_repository import PostgresAuditLogRepository

__all__ = [
    "PostgresDocumentRepository",
    "PostgresProjectRepository",
    "PostgresIssueRepository",
    "PostgresIngestionJobRepository",
    "PostgresConsumerRepository",
    "PostgresPermissionRepository",
    "PostgresAuditLogRepository",
]
