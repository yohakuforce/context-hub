"""Audit context — immutable append-only audit log.

All operations (ingestion / query / permission change) are recorded here.
AuditLog entries are NEVER updated or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from src.shared.types import AuditLogId, ConsumerId, ProjectId, new_id


class OperationType(str, Enum):
    """Types of operations recorded in the audit log."""

    # Ingestion operations
    INGESTION_STARTED = "ingestion_started"
    INGESTION_COMPLETED = "ingestion_completed"
    INGESTION_FAILED = "ingestion_failed"

    # Query operations
    QUERY_EXECUTED = "query_executed"

    # Access control events
    PERMISSION_DENIED = "permission_denied"
    API_KEY_CREATED = "api_key_created"
    API_KEY_ROTATED = "api_key_rotated"

    # Data mutations
    DOCUMENT_SAVED = "document_saved"
    ISSUE_SAVED = "issue_saved"


@dataclass(frozen=True)
class AuditLog:
    """Immutable audit log entry.

    Once written, never modified. Repository only supports append + read.
    """

    id: AuditLogId
    operation_type: OperationType
    consumer_id: Optional[ConsumerId]
    project_id: Optional[ProjectId]
    resource_id: Optional[str]
    metadata: dict[str, Any]          # extra context (query text, error msg, etc.)
    occurred_at: datetime

    @classmethod
    def create(
        cls,
        operation_type: OperationType,
        consumer_id: Optional[ConsumerId] = None,
        project_id: Optional[ProjectId] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "AuditLog":
        return cls(
            id=AuditLogId(new_id()),
            operation_type=operation_type,
            consumer_id=consumer_id,
            project_id=project_id,
            resource_id=resource_id,
            metadata=metadata or {},
            occurred_at=datetime.utcnow(),
        )
