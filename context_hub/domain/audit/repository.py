"""AuditLog repository interface — append-only."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from context_hub.domain.audit.entities import AuditLog, OperationType
from context_hub.shared.types import ConsumerId, ProjectId


class AuditLogRepository(ABC):
    """Append-only repository for AuditLog entries.

    No update or delete methods — this is intentional.
    """

    @abstractmethod
    async def append(self, log: AuditLog) -> None:
        """Write a new audit log entry."""
        ...

    @abstractmethod
    async def find_by_consumer(
        self,
        consumer_id: ConsumerId,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        ...

    @abstractmethod
    async def find_by_project(
        self,
        project_id: ProjectId,
        operation_type: Optional[OperationType] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        ...
