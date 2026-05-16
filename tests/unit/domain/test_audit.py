"""Unit tests for audit domain entities."""

from __future__ import annotations

import pytest
from datetime import datetime

from src.domain.audit.entities import AuditLog, OperationType
from src.shared.types import AuditLogId, ConsumerId, ProjectId


class TestAuditLog:
    def test_create_audit_log(self):
        log = AuditLog.create(
            operation_type=OperationType.QUERY_EXECUTED,
            consumer_id=ConsumerId("consumer-001"),
            project_id=ProjectId("project-001"),
            metadata={"query": "search term"},
        )
        assert log.consumer_id == ConsumerId("consumer-001")
        assert log.operation_type == OperationType.QUERY_EXECUTED
        assert log.project_id == ProjectId("project-001")
        assert log.metadata["query"] == "search term"

    def test_audit_log_has_id(self):
        log = AuditLog.create(operation_type=OperationType.INGESTION_STARTED)
        assert log.id is not None
        assert len(str(log.id)) == 36  # UUID format

    def test_audit_log_timestamp_set(self):
        log = AuditLog.create(operation_type=OperationType.QUERY_EXECUTED)
        assert log.occurred_at is not None
        assert isinstance(log.occurred_at, datetime)

    def test_audit_log_without_project_id(self):
        log = AuditLog.create(
            operation_type=OperationType.INGESTION_STARTED,
            project_id=None,
        )
        assert log.project_id is None

    def test_audit_log_without_optional_fields(self):
        log = AuditLog.create(operation_type=OperationType.INGESTION_FAILED)
        assert log.consumer_id is None
        assert log.project_id is None
        assert log.resource_id is None
        assert log.metadata == {}

    def test_all_operation_types_are_defined(self):
        """Verify expected operation types exist."""
        assert OperationType.QUERY_EXECUTED is not None
        assert OperationType.INGESTION_STARTED is not None
        assert OperationType.INGESTION_COMPLETED is not None
        assert OperationType.INGESTION_FAILED is not None
        assert OperationType.PERMISSION_DENIED is not None

    def test_audit_log_is_immutable(self):
        """AuditLog is a frozen dataclass — mutation should raise."""
        log = AuditLog.create(operation_type=OperationType.QUERY_EXECUTED)
        with pytest.raises((AttributeError, TypeError)):
            log.metadata = {"changed": True}  # type: ignore
