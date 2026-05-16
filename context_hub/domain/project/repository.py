"""Project repository interface.

Concrete implementations live in src/infrastructure/db/.
"""

from abc import ABC, abstractmethod
from typing import Optional

from context_hub.domain.project.entities import Project
from context_hub.shared.types import ProjectId


class ProjectRepository(ABC):
    """Abstract repository for the Project aggregate."""

    @abstractmethod
    async def find_by_id(self, project_id: ProjectId) -> Optional[Project]:
        """Return the Project with the given ID, or None if not found."""
        ...

    @abstractmethod
    async def find_all(self) -> list[Project]:
        """Return all Projects."""
        ...

    @abstractmethod
    async def find_by_external_id(self, external_project_id: str) -> Optional[Project]:
        """Return the Project linked to the given external ID, or None."""
        ...

    @abstractmethod
    async def save(self, project: Project) -> Project:
        """Persist a Project (insert or update). Returns the saved instance."""
        ...

    @abstractmethod
    async def delete(self, project_id: ProjectId) -> None:
        """Delete a Project by ID."""
        ...
