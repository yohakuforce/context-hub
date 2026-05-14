"""Issue repository interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from src.domain.issue.entities import Issue
from src.shared.types import IssueId, IssueStatus, ProjectId, SourceType


class IssueRepository(ABC):
    """Abstract repository for the Issue aggregate."""

    @abstractmethod
    async def find_by_id(self, issue_id: IssueId) -> Optional[Issue]:
        ...

    @abstractmethod
    async def find_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
        status: Optional[IssueStatus] = None,
        assignee_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Issue]:
        ...

    @abstractmethod
    async def find_updated_since(
        self,
        project_id: ProjectId,
        source_type: SourceType,
        since: datetime,
    ) -> list[Issue]:
        """Used for incremental sync — returns issues updated after `since`."""
        ...

    @abstractmethod
    async def find_by_external_id(
        self,
        project_id: ProjectId,
        source_type: SourceType,
        external_id: str,
    ) -> Optional[Issue]:
        """Used for upsert deduplication."""
        ...

    @abstractmethod
    async def count_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
    ) -> int:
        ...

    @abstractmethod
    async def save(self, issue: Issue) -> Issue:
        """Upsert based on (project_id, source_type, external_id)."""
        ...

    @abstractmethod
    async def save_many(self, issues: list[Issue]) -> list[Issue]:
        """Batch upsert for efficiency during full resync."""
        ...
