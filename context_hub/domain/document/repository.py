"""Document repository interface."""

from abc import ABC, abstractmethod
from typing import Optional

from context_hub.domain.document.entities import Document
from context_hub.shared.types import DocumentId, EmbeddingVector, ProjectId, SourceType


class DocumentRepository(ABC):
    """Abstract repository for the Document aggregate."""

    @abstractmethod
    async def find_by_id(self, doc_id: DocumentId) -> Optional[Document]:
        ...

    @abstractmethod
    async def find_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Document]:
        ...

    @abstractmethod
    async def find_by_external_id(
        self,
        project_id: ProjectId,
        source_type: SourceType,
        external_id: str,
    ) -> Optional[Document]:
        """Used for upsert deduplication."""
        ...

    @abstractmethod
    async def find_similar(
        self,
        vector: EmbeddingVector,
        project_id: ProjectId,
        top_k: int = 10,
        source_types: Optional[list[SourceType]] = None,
    ) -> list[tuple[Document, float]]:
        """Return the top-k most similar Documents with their cosine scores."""
        ...

    @abstractmethod
    async def count_by_project(
        self,
        project_id: ProjectId,
        source_type: Optional[SourceType] = None,
    ) -> int:
        ...

    @abstractmethod
    async def save(self, document: Document) -> Document:
        """Upsert based on (project_id, source_type, external_id)."""
        ...
