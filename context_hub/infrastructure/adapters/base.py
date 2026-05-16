"""Base class for all Source adapters.

Each adapter is responsible for:
1. Fetching raw data from its source system (Slack / Backlog / Redmine / etc.)
2. Normalising the raw data into domain objects (Document / Issue / Comment)
3. Returning a new SyncCursor that marks where the next sync should start

Adapters do NOT persist data — that responsibility belongs to the use-case layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from context_hub.domain.document.entities import Document
from context_hub.domain.issue.entities import Issue
from context_hub.shared.types import ProjectId, SourceType, SyncCursor


@dataclass
class IngestionResult:
    """Output from a single adapter sync run."""

    documents: list[Document]
    issues: list[Issue]
    new_cursor: SyncCursor | None   # None = cursor unchanged (no new items)
    error_count: int = 0
    skipped_count: int = 0


class SourceAdapter(ABC):
    """Abstract base for all source adapters."""

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        ...

    @abstractmethod
    async def fetch(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
        full_resync: bool = False,
    ) -> IngestionResult:
        """Fetch new/updated items from the source.

        Args:
            project_id: The Context-Hub project this fetch belongs to.
            cursor: The last known sync position. None = first ever run.
            full_resync: If True, ignore cursor and fetch everything.

        Returns:
            IngestionResult with normalised domain objects and the new cursor.
        """
        ...
