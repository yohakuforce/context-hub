"""Backward-compatibility shim for PostgresAuditLogRepository.

The canonical implementation lives in:
    src/adapters/postgres/audit_log_repository.py
"""

from context_hub.adapters.postgres.audit_log_repository import (  # noqa: F401
    PostgresAuditLogRepository,
    _row_to_domain,
)

__all__ = [
    "PostgresAuditLogRepository",
    "_row_to_domain",
]
