"""IngestionJob aggregate root.

Tracks the lifecycle of a single ingestion run for one Source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.shared.types import (
    IngestionJobId,
    JobStatus,
    ProjectId,
    SourceType,
    SyncCursor,
    SyncError,
    new_id,
)


@dataclass
class IngestionJob:
    """Aggregate root tracking a single ingestion run.

    State transitions:
        PENDING → RUNNING → COMPLETED
                          → FAILED
    """

    id: IngestionJobId
    project_id: ProjectId
    source_type: SourceType
    status: JobStatus
    sync_cursor: Optional[SyncCursor]
    items_processed: int
    errors: list[SyncError]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        project_id: ProjectId,
        source_type: SourceType,
        sync_cursor: Optional[SyncCursor] = None,
    ) -> "IngestionJob":
        now = datetime.utcnow()
        return cls(
            id=IngestionJobId(new_id()),
            project_id=project_id,
            source_type=source_type,
            status=JobStatus.PENDING,
            sync_cursor=sync_cursor,
            items_processed=0,
            errors=[],
            started_at=None,
            finished_at=None,
            created_at=now,
        )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def start(self) -> "IngestionJob":
        """Mark the job as RUNNING."""
        if self.status != JobStatus.PENDING:
            raise ValueError(
                f"Cannot start job {self.id}: current status is {self.status}"
            )
        return IngestionJob(
            id=self.id,
            project_id=self.project_id,
            source_type=self.source_type,
            status=JobStatus.RUNNING,
            sync_cursor=self.sync_cursor,
            items_processed=self.items_processed,
            errors=list(self.errors),
            started_at=datetime.utcnow(),
            finished_at=None,
            created_at=self.created_at,
        )

    def complete(
        self,
        items_processed: int,
        new_cursor: Optional[SyncCursor] = None,
    ) -> "IngestionJob":
        """Mark the job as COMPLETED and update the sync cursor."""
        return IngestionJob(
            id=self.id,
            project_id=self.project_id,
            source_type=self.source_type,
            status=JobStatus.COMPLETED,
            sync_cursor=new_cursor or self.sync_cursor,
            items_processed=items_processed,
            errors=list(self.errors),
            started_at=self.started_at,
            finished_at=datetime.utcnow(),
            created_at=self.created_at,
        )

    def fail(self, errors: list[SyncError]) -> "IngestionJob":
        """Mark the job as FAILED.

        Per the design: item-level errors are accumulated (best-effort).
        A job is only moved to FAILED when it cannot continue at all.
        """
        return IngestionJob(
            id=self.id,
            project_id=self.project_id,
            source_type=self.source_type,
            status=JobStatus.FAILED,
            sync_cursor=self.sync_cursor,  # cursor NOT advanced on failure
            items_processed=self.items_processed,
            errors=list(self.errors) + list(errors),
            started_at=self.started_at,
            finished_at=datetime.utcnow(),
            created_at=self.created_at,
        )

    def record_item_error(self, error: SyncError) -> "IngestionJob":
        """Record a single item-level error without changing overall status."""
        return IngestionJob(
            id=self.id,
            project_id=self.project_id,
            source_type=self.source_type,
            status=self.status,
            sync_cursor=self.sync_cursor,
            items_processed=self.items_processed,
            errors=list(self.errors) + [error],
            started_at=self.started_at,
            finished_at=self.finished_at,
            created_at=self.created_at,
        )
