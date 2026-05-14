"""Access Control repository interfaces."""

from abc import ABC, abstractmethod
from typing import Optional

from src.domain.access_control.entities import Consumer, Permission
from src.shared.types import ConsumerId, PermissionId, ProjectId


class ConsumerRepository(ABC):
    @abstractmethod
    async def find_by_id(self, consumer_id: ConsumerId) -> Optional[Consumer]:
        ...

    @abstractmethod
    async def find_by_api_key_prefix(self, prefix: str) -> Optional[Consumer]:
        """Look up Consumer by a non-secret prefix (consumer_id portion of the key)."""
        ...

    @abstractmethod
    async def find_all_active(self) -> list[Consumer]:
        ...

    @abstractmethod
    async def save(self, consumer: Consumer) -> Consumer:
        ...


class PermissionRepository(ABC):
    @abstractmethod
    async def find_by_consumer(self, consumer_id: ConsumerId) -> list[Permission]:
        ...

    @abstractmethod
    async def find_by_consumer_and_project(
        self,
        consumer_id: ConsumerId,
        project_id: ProjectId,
    ) -> Optional[Permission]:
        """Return a Permission that covers the given project, or None."""
        ...

    @abstractmethod
    async def save(self, permission: Permission) -> Permission:
        ...

    @abstractmethod
    async def delete(self, permission_id: PermissionId) -> None:
        ...
