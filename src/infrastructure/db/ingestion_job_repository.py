"""PostgreSQL implementation of IngestionJobRepository."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.ingestion.entities import IngestionJob
from src.domain.ingestion.repository import IngestionJobRepository
from src.infrastructure.db.models import IngestionJobRow
from src.shared.types import (
    IngestionJobId,
    JobStatus,
    ProjectId,
    SourceType,
    SyncCursor,
    SyncError,
)


class PostgresIngestionJobRepository(IngestionJobRepository):
    """Concrete IngestionJob repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, job_id: IngestionJobId) -> Optional[IngestionJob]:
        row = await self._session.get(IngestionJobRow, str(job_id))
        return _row_to_domain(row) if row else None

    async def find_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
        status: Optional[JobStatus] = None,
        limit: int = 20,
    ) -> list[IngestionJob]:
        q = (
            select(IngestionJobRow)
            .where(IngestionJobRow.project_id == str(project_id))
            .order_by(IngestionJobRow.created_at.desc())
            .limit(limit)
        )
        if source_type:
            q = q.where(IngestionJobRow.source_type == source_type.value)
        if status:
            q = q.where(IngestionJobRow.status == status.value)
        result = await self._session.execute(q)
        return [_row_to_domain(r) for r in result.scalars().all()]

    async def find_latest_completed(
        self,
        project_id: ProjectId,
        source_type: SourceType,
    ) -> Optional[IngestionJob]:
        """Return the most recently completed job for a given source."""
        result = await self._session.execute(
            select(IngestionJobRow)
            .where(
                IngestionJobRow.project_id == str(project_id),
                IngestionJobRow.source_type == source_type.value,
                IngestionJobRow.status == JobStatus.COMPLETED.value,
            )
            .order_by(IngestionJobRow.finished_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _row_to_domain(row) if row else None

    async def save(self, job: IngestionJob) -> IngestionJob:
        existing = await self._session.get(IngestionJobRow, str(job.id))
        if existing is None:
            self._session.add(_domain_to_row(job))
        else:
            existing.status = job.status.value
            existing.sync_cursor_source_type = (
                job.sync_cursor.source_type.value if job.sync_cursor else None
            )
            existing.sync_cursor_value = (
                job.sync_cursor.cursor_value if job.sync_cursor else None
            )
            existing.items_processed = job.items_processed
            existing.errors = [
                {
                    "item_id": e.item_id,
                    "message": e.message,
                    "occurred_at": e.occurred_at.isoformat(),
                }
                for e in job.errors
            ]
            existing.started_at = job.started_at
            existing.finished_at = job.finished_at
        return job


def _domain_to_row(job: IngestionJob) -> IngestionJobRow:
    return IngestionJobRow(
        id=str(job.id),
        project_id=str(job.project_id),
        source_type=job.source_type.value,
        status=job.status.value,
        sync_cursor_source_type=(
            job.sync_cursor.source_type.value if job.sync_cursor else None
        ),
        sync_cursor_value=(
            job.sync_cursor.cursor_value if job.sync_cursor else None
        ),
        items_processed=job.items_processed,
        errors=[
            {
                "item_id": e.item_id,
                "message": e.message,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in job.errors
        ],
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )


def _row_to_domain(row: IngestionJobRow) -> IngestionJob:
    sync_cursor = None
    if row.sync_cursor_source_type and row.sync_cursor_value:
        sync_cursor = SyncCursor(
            source_type=SourceType(row.sync_cursor_source_type),
            cursor_value=row.sync_cursor_value,
        )

    errors = [
        SyncError(
            item_id=e["item_id"],
            message=e["message"],
            occurred_at=datetime.fromisoformat(e["occurred_at"]),
        )
        for e in (row.errors or [])
    ]

    return IngestionJob(
        id=IngestionJobId(row.id),
        project_id=ProjectId(row.project_id),
        source_type=SourceType(row.source_type),
        status=JobStatus(row.status),
        sync_cursor=sync_cursor,
        items_processed=row.items_processed,
        errors=errors,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
    )
