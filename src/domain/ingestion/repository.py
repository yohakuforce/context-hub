"""IngestionJob repository interface."""

from abc import ABC, abstractmethod
from typing import Optional

from src.domain.ingestion.entities import IngestionJob
from src.shared.types import IngestionJobId, JobStatus, ProjectId, SourceType


class IngestionJobRepository(ABC):
    """Abstract repository for the IngestionJob aggregate."""

    @abstractmethod
    async def find_by_id(self, job_id: IngestionJobId) -> Optional[IngestionJob]:
        ...

    @abstractmethod
    async def find_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
        status: Optional[JobStatus] = None,
        limit: int = 20,
    ) -> list[IngestionJob]:
        ...

    @abstractmethod
    async def find_latest_completed(
        self,
        project_id: ProjectId,
        source_type: SourceType,
    ) -> Optional[IngestionJob]:
        """Return the most recently completed job — used to retrieve the last SyncCursor."""
        ...

    @abstractmethod
    async def save(self, job: IngestionJob) -> IngestionJob:
        ...
