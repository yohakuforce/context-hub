"""Unit tests for PostgresIngestionJobRepository mapping logic."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from context_hub.domain.ingestion.entities import IngestionJob
from context_hub.infrastructure.db.ingestion_job_repository import (
    PostgresIngestionJobRepository,
    _domain_to_row,
    _row_to_domain,
)
from context_hub.infrastructure.db.models import IngestionJobRow
from context_hub.shared.types import (
    IngestionJobId,
    JobStatus,
    ProjectId,
    SourceType,
    SyncCursor,
    SyncError,
)


def _make_job() -> IngestionJob:
    return IngestionJob.create(
        project_id=ProjectId("proj-001"),
        source_type=SourceType.SLACK,
    )


def _make_job_row(job: IngestionJob) -> IngestionJobRow:
    row = IngestionJobRow()
    row.id = str(job.id)
    row.project_id = str(job.project_id)
    row.source_type = job.source_type.value
    row.status = job.status.value
    row.sync_cursor_source_type = None
    row.sync_cursor_value = None
    row.items_processed = 0
    row.errors = []
    row.started_at = None
    row.finished_at = None
    row.created_at = job.created_at
    return row


class TestDomainToRow:
    def test_pending_job(self) -> None:
        job = _make_job()
        row = _domain_to_row(job)
        assert row.id == str(job.id)
        assert row.status == "pending"
        assert row.sync_cursor_source_type is None
        assert row.sync_cursor_value is None
        assert row.errors == []

    def test_job_with_cursor(self) -> None:
        job = _make_job()
        cursor = SyncCursor(source_type=SourceType.SLACK, cursor_value="2026-05-01T00:00:00")
        completed_job = job.start().complete(items_processed=10, new_cursor=cursor)
        row = _domain_to_row(completed_job)
        assert row.status == "completed"
        assert row.sync_cursor_source_type == "slack"
        assert row.sync_cursor_value == "2026-05-01T00:00:00"
        assert row.items_processed == 10

    def test_job_with_errors(self) -> None:
        job = _make_job()
        error = SyncError(
            item_id="msg-001",
            message="Parse failed",
            occurred_at=datetime(2026, 5, 1, 9, 0),
        )
        failed_job = job.start().fail([error])
        row = _domain_to_row(failed_job)
        assert row.status == "failed"
        assert len(row.errors) == 1
        assert row.errors[0]["item_id"] == "msg-001"


class TestRowToDomain:
    def test_basic_pending_row(self) -> None:
        job = _make_job()
        row = _make_job_row(job)
        result = _row_to_domain(row)
        assert result.id == job.id
        assert result.status == JobStatus.PENDING
        assert result.sync_cursor is None
        assert result.errors == []

    def test_row_with_cursor(self) -> None:
        job = _make_job()
        row = _make_job_row(job)
        row.sync_cursor_source_type = "slack"
        row.sync_cursor_value = "2026-05-01T00:00:00"
        result = _row_to_domain(row)
        assert result.sync_cursor is not None
        assert result.sync_cursor.source_type == SourceType.SLACK

    def test_row_with_errors(self) -> None:
        job = _make_job()
        row = _make_job_row(job)
        row.errors = [
            {
                "item_id": "item-1",
                "message": "Something went wrong",
                "occurred_at": "2026-05-01T09:00:00",
            }
        ]
        result = _row_to_domain(row)
        assert len(result.errors) == 1
        assert result.errors[0].message == "Something went wrong"


class TestPostgresIngestionJobRepository:
    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        repo = PostgresIngestionJobRepository(session)
        result = await repo.find_by_id(IngestionJobId("not-found"))
        assert result is None

    @pytest.mark.asyncio
    async def test_save_new_job_adds_to_session(self) -> None:
        job = _make_job()
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        session.add = MagicMock()
        repo = PostgresIngestionJobRepository(session)
        result = await repo.save(job)
        assert result is job
        session.add.assert_called_once()
