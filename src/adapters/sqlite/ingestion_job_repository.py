"""SQLite implementation of IngestionJobRepository."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime
from typing import Any, cast

from src.adapters.sqlite.session import open_connection
from src.domain.ingestion.entities import IngestionJob
from src.domain.ingestion.repository import IngestionJobRepository
from src.shared.types import (
    IngestionJobId,
    JobStatus,
    ProjectId,
    SourceType,
    SyncCursor,
    SyncError,
)


class SqliteIngestionJobRepository(IngestionJobRepository):
    """Concrete IngestionJobRepository backed by SQLite.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def find_by_id(self, job_id: IngestionJobId) -> IngestionJob | None:
        """Return the IngestionJob with the given ID, or None.

        Args:
            job_id: UUID string identifying the job.

        Returns:
            IngestionJob domain object, or None.
        """
        row = await asyncio.to_thread(self._sync_find_by_id, str(job_id))
        return _row_to_domain(row) if row else None

    async def find_by_project(
        self,
        project_id: ProjectId,
        source_type: SourceType | None = None,
        status: JobStatus | None = None,
        limit: int = 20,
    ) -> list[IngestionJob]:
        """Return ingestion jobs for a project with optional filters.

        Args:
            project_id:  UUID string identifying the project.
            source_type: Optional filter for source type.
            status:      Optional filter for job status.
            limit:       Maximum number of results.

        Returns:
            List of IngestionJob objects ordered by created_at descending.
        """
        rows = await asyncio.to_thread(
            self._sync_find_by_project, str(project_id), source_type, status, limit
        )
        return [_row_to_domain(r) for r in rows]

    async def find_latest_completed(
        self,
        project_id: ProjectId,
        source_type: SourceType,
    ) -> IngestionJob | None:
        """Return the most recently completed job for a given source.

        Args:
            project_id:  UUID string identifying the project.
            source_type: Source type to filter.

        Returns:
            Most recent completed IngestionJob, or None if no completed jobs exist.
        """
        row = await asyncio.to_thread(
            self._sync_find_latest_completed,
            str(project_id), source_type.value,
        )
        return _row_to_domain(row) if row else None

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def save(self, job: IngestionJob) -> IngestionJob:
        """Upsert an IngestionJob (keyed on id).

        Args:
            job: IngestionJob domain object to persist.

        Returns:
            The same IngestionJob instance (unchanged).
        """
        await asyncio.to_thread(self._sync_save, job)
        return job

    # ------------------------------------------------------------------
    # Synchronous helpers
    # ------------------------------------------------------------------

    _SELECT_COLS = (
        "id, project_id, source_type, status, "
        "sync_cursor_source_type, sync_cursor_value, "
        "items_processed, errors, started_at, finished_at, created_at"
    )

    def _sync_find_by_id(self, job_id: str) -> sqlite3.Row | None:
        with open_connection(self._db_path) as conn:
            return cast(
                sqlite3.Row | None,
                conn.execute(
                    f"SELECT {self._SELECT_COLS} FROM ingestion_jobs WHERE id = ?",  # noqa: S608
                    (job_id,),
                ).fetchone(),
            )

    def _sync_find_by_project(
        self,
        project_id: str,
        source_type: SourceType | None,
        status: JobStatus | None,
        limit: int,
    ) -> list[sqlite3.Row]:
        with open_connection(self._db_path) as conn:
            sql = (
                f"SELECT {self._SELECT_COLS} FROM ingestion_jobs "  # noqa: S608
                "WHERE project_id = ? "
            )
            params: list[object] = [project_id]
            if source_type:
                sql += "AND source_type = ? "
                params.append(source_type.value)
            if status:
                sql += "AND status = ? "
                params.append(status.value)
            sql += "ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            return conn.execute(sql, params).fetchall()

    def _sync_find_latest_completed(
        self, project_id: str, source_type: str
    ) -> sqlite3.Row | None:
        with open_connection(self._db_path) as conn:
            return cast(
                sqlite3.Row | None,
                conn.execute(
                    f"SELECT {self._SELECT_COLS} FROM ingestion_jobs "  # noqa: S608
                    "WHERE project_id = ? AND source_type = ? AND status = ? "
                    "ORDER BY finished_at DESC LIMIT 1",
                    (project_id, source_type, JobStatus.COMPLETED.value),
                ).fetchone(),
            )

    def _sync_save(self, job: IngestionJob) -> None:
        v = _domain_to_values(job)
        with open_connection(self._db_path) as conn:
            conn.execute(
                "INSERT INTO ingestion_jobs ("
                "  id, project_id, source_type, status, "
                "  sync_cursor_source_type, sync_cursor_value, "
                "  items_processed, errors, started_at, finished_at, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "  status = excluded.status, "
                "  sync_cursor_source_type = excluded.sync_cursor_source_type, "
                "  sync_cursor_value = excluded.sync_cursor_value, "
                "  items_processed = excluded.items_processed, "
                "  errors = excluded.errors, "
                "  started_at = excluded.started_at, "
                "  finished_at = excluded.finished_at",
                (
                    v["id"], v["project_id"], v["source_type"], v["status"],
                    v["sync_cursor_source_type"], v["sync_cursor_value"],
                    v["items_processed"], v["errors"],
                    v["started_at"], v["finished_at"], v["created_at"],
                ),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _domain_to_values(job: IngestionJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "source_type": job.source_type.value,
        "status": job.status.value,
        "sync_cursor_source_type": (
            job.sync_cursor.source_type.value if job.sync_cursor else None
        ),
        "sync_cursor_value": (
            job.sync_cursor.cursor_value if job.sync_cursor else None
        ),
        "items_processed": job.items_processed,
        "errors": json.dumps(
            [
                {
                    "item_id": e.item_id,
                    "message": e.message,
                    "occurred_at": e.occurred_at.isoformat(),
                }
                for e in job.errors
            ]
        ),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat(),
    }


def _row_to_domain(row: sqlite3.Row) -> IngestionJob:
    (
        job_id, project_id, source_type, status,
        cursor_st, cursor_val,
        items_processed, errors_json, started_at, finished_at, created_at,
    ) = row

    sync_cursor = None
    if cursor_st and cursor_val:
        sync_cursor = SyncCursor(
            source_type=SourceType(cursor_st),
            cursor_value=cursor_val,
        )

    errors = [
        SyncError(
            item_id=e["item_id"],
            message=e["message"],
            occurred_at=datetime.fromisoformat(e["occurred_at"]),
        )
        for e in json.loads(errors_json or "[]")
    ]

    return IngestionJob(
        id=IngestionJobId(job_id),
        project_id=ProjectId(project_id),
        source_type=SourceType(source_type),
        status=JobStatus(status),
        sync_cursor=sync_cursor,
        items_processed=items_processed,
        errors=errors,
        started_at=datetime.fromisoformat(started_at) if started_at else None,
        finished_at=datetime.fromisoformat(finished_at) if finished_at else None,
        created_at=datetime.fromisoformat(created_at),
    )
