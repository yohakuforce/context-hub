"""Unit tests for IngestionJob aggregate state transitions."""

import pytest
from datetime import datetime

from context_hub.domain.ingestion.entities import IngestionJob
from context_hub.shared.types import (
    IngestionJobId,
    JobStatus,
    ProjectId,
    SourceType,
    SyncCursor,
    SyncError,
    new_id,
)


def make_job() -> IngestionJob:
    return IngestionJob.create(
        project_id=ProjectId(new_id()),
        source_type=SourceType.BACKLOG,
    )


class TestIngestionJobCreate:
    def test_initial_status_is_pending(self):
        job = make_job()
        assert job.status == JobStatus.PENDING

    def test_initial_items_processed_is_zero(self):
        job = make_job()
        assert job.items_processed == 0

    def test_initial_errors_is_empty(self):
        job = make_job()
        assert job.errors == []


class TestIngestionJobStart:
    def test_start_transitions_to_running(self):
        job = make_job()
        running = job.start()
        assert running.status == JobStatus.RUNNING

    def test_start_sets_started_at(self):
        job = make_job()
        running = job.start()
        assert running.started_at is not None

    def test_start_does_not_mutate_original(self):
        job = make_job()
        job.start()
        assert job.status == JobStatus.PENDING

    def test_cannot_start_running_job(self):
        job = make_job().start()
        with pytest.raises(ValueError, match="Cannot start"):
            job.start()


class TestIngestionJobComplete:
    def test_complete_transitions_to_completed(self):
        job = make_job().start()
        completed = job.complete(items_processed=42)
        assert completed.status == JobStatus.COMPLETED

    def test_complete_sets_items_processed(self):
        job = make_job().start()
        completed = job.complete(items_processed=100)
        assert completed.items_processed == 100

    def test_complete_updates_cursor(self):
        job = make_job().start()
        new_cursor = SyncCursor(source_type=SourceType.BACKLOG, cursor_value="2026-05-15T00:00:00Z")
        completed = job.complete(items_processed=5, new_cursor=new_cursor)
        assert completed.sync_cursor == new_cursor

    def test_complete_sets_finished_at(self):
        job = make_job().start()
        completed = job.complete(items_processed=0)
        assert completed.finished_at is not None


class TestIngestionJobFail:
    def test_fail_transitions_to_failed(self):
        job = make_job().start()
        errors = [SyncError(item_id="1", message="oops", occurred_at=datetime.utcnow())]
        failed = job.fail(errors)
        assert failed.status == JobStatus.FAILED

    def test_fail_preserves_cursor(self):
        cursor = SyncCursor(source_type=SourceType.BACKLOG, cursor_value="2026-05-14T00:00:00Z")
        job = IngestionJob.create(
            project_id=ProjectId(new_id()),
            source_type=SourceType.BACKLOG,
            sync_cursor=cursor,
        )
        running = job.start()
        failed = running.fail([])
        # Cursor should NOT advance on failure
        assert failed.sync_cursor == cursor


class TestIngestionJobRecordItemError:
    def test_record_item_error_accumulates_errors(self):
        job = make_job().start()
        err = SyncError(item_id="x", message="bad", occurred_at=datetime.utcnow())
        updated = job.record_item_error(err)
        assert len(updated.errors) == 1

    def test_record_item_error_does_not_change_status(self):
        job = make_job().start()
        err = SyncError(item_id="x", message="bad", occurred_at=datetime.utcnow())
        updated = job.record_item_error(err)
        assert updated.status == JobStatus.RUNNING
