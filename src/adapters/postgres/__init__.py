"""PostgreSQL / pgvector adapter package.

Re-exports all Postgres repository implementations so that the rest of the
codebase can import from a single, stable location.
"""

from src.adapters.postgres.document_repository import PostgresDocumentRepository
from src.adapters.postgres.project_repository import PostgresProjectRepository
from src.adapters.postgres.issue_repository import PostgresIssueRepository
from src.adapters.postgres.ingestion_job_repository import PostgresIngestionJobRepository
from src.adapters.postgres.access_control_repository import (
    PostgresConsumerRepository,
    PostgresPermissionRepository,
)
from src.adapters.postgres.audit_log_repository import PostgresAuditLogRepository

__all__ = [
    "PostgresDocumentRepository",
    "PostgresProjectRepository",
    "PostgresIssueRepository",
    "PostgresIngestionJobRepository",
    "PostgresConsumerRepository",
    "PostgresPermissionRepository",
    "PostgresAuditLogRepository",
]
