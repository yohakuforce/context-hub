"""Tests for SqliteIngestionJobRepository."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
import sqlite_vec

from context_hub.adapters.sqlite.ingestion_job_repository import SqliteIngestionJobRepository
from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
from context_hub.domain.ingestion.entities import IngestionJob
from context_hub.domain.project.entities import Project
from context_hub.shared.types import (
    IngestionJobId,
    JobStatus,
    ProjectId,
    SourceType,
    SyncCursor,
    SyncError,
    new_id,
)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "job_test.db")
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    schema = (
        Path(__file__).parent.parent.parent.parent.parent
        / "context_hub" / "_sqlite_schema" / "001_init.sql"
    )
    conn.executescript(schema.read_text(encoding="utf-8"))
    conn.close()
    return path


@pytest.fixture
async def project_id(db_path: str) -> ProjectId:
    pid = ProjectId(new_id())
    project = Project(
        id=pid,
        name="Test Project",
        external_project_id=None,
        sources=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    await SqliteProjectRepository(db_path).save(project)
    return pid


def _make_job(project_id: ProjectId) -> IngestionJob:
    return IngestionJob.create(
        project_id=project_id,
        source_type=SourceType.SLACK,
    )


@pytest.mark.asyncio
class TestSqliteIngestionJobRepository:
    async def test_find_by_id_returns_none_when_missing(
        self, db_path: str
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        result = await repo.find_by_id(IngestionJobId(new_id()))
        assert result is None

    async def test_save_and_find_by_id(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        job = _make_job(project_id)
        await repo.save(job)
        found = await repo.find_by_id(job.id)
        assert found is not None
        assert found.id == job.id
        assert found.status == JobStatus.PENDING

    async def test_find_by_project(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        job = _make_job(project_id)
        await repo.save(job)
        results = await repo.find_by_project(project_id)
        assert any(j.id == job.id for j in results)

    async def test_find_by_project_source_type_filter(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        slack_job = IngestionJob.create(project_id=project_id, source_type=SourceType.SLACK)
        backlog_job = IngestionJob.create(project_id=project_id, source_type=SourceType.BACKLOG)
        await repo.save(slack_job)
        await repo.save(backlog_job)
        results = await repo.find_by_project(project_id, source_type=SourceType.SLACK)
        assert all(j.source_type == SourceType.SLACK for j in results)

    async def test_find_by_project_status_filter(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        job = _make_job(project_id)
        running = job.start()
        await repo.save(running)
        results = await repo.find_by_project(
            project_id, status=JobStatus.RUNNING
        )
        assert len(results) == 1
        assert results[0].status == JobStatus.RUNNING

    async def test_find_by_project_limit(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        for _ in range(5):
            await repo.save(_make_job(project_id))
        results = await repo.find_by_project(project_id, limit=2)
        assert len(results) <= 2

    async def test_find_latest_completed_returns_none_when_none(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        result = await repo.find_latest_completed(project_id, SourceType.SLACK)
        assert result is None

    async def test_find_latest_completed_returns_completed_job(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        job = _make_job(project_id)
        running = job.start()
        completed = running.complete(items_processed=5)
        await repo.save(completed)
        result = await repo.find_latest_completed(project_id, SourceType.SLACK)
        assert result is not None
        assert result.status == JobStatus.COMPLETED

    async def test_save_is_upsert_status_update(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        job = _make_job(project_id)
        await repo.save(job)
        running = job.start()
        await repo.save(running)
        found = await repo.find_by_id(job.id)
        assert found is not None
        assert found.status == JobStatus.RUNNING

    async def test_job_with_sync_cursor_roundtrip(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        job = _make_job(project_id)
        running = job.start()
        cursor = SyncCursor(source_type=SourceType.SLACK, cursor_value="2026-01-01T00:00:00")
        completed = running.complete(items_processed=10, new_cursor=cursor)
        await repo.save(completed)
        found = await repo.find_by_id(job.id)
        assert found is not None
        assert found.sync_cursor is not None
        assert found.sync_cursor.cursor_value == "2026-01-01T00:00:00"

    async def test_job_with_errors_roundtrip(
        self, db_path: str, project_id: ProjectId
    ) -> None:
        repo = SqliteIngestionJobRepository(db_path)
        job = _make_job(project_id)
        running = job.start()
        error = SyncError(
            item_id="item-1",
            message="fetch failed",
            occurred_at=datetime.utcnow(),
        )
        failed = running.fail([error])
        await repo.save(failed)
        found = await repo.find_by_id(job.id)
        assert found is not None
        assert found.status == JobStatus.FAILED
        assert len(found.errors) == 1
        assert found.errors[0].item_id == "item-1"
