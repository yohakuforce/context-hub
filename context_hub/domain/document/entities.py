"""Document aggregate root.

A Document represents a single ingested unit from any Source —
one Slack thread, one meeting transcript, one wiki page, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from context_hub.shared.types import (
    DocumentId,
    EmbeddingVector,
    IngestionJobId,
    ProjectId,
    RawContent,
    SourceType,
    StructuredContent,
    new_id,
)


@dataclass
class Document:
    """Aggregate root for a single ingested context unit.

    Immutable-update pattern: mutations return new Document instances
    rather than modifying in place.
    """

    id: DocumentId
    project_id: ProjectId
    source_type: SourceType
    # The original ID in the source system (Slack ts, Backlog wiki ID, etc.)
    external_id: str
    raw_content: RawContent          # immutable once set
    structured_content: StructuredContent | None
    embedding_vector: EmbeddingVector | None
    ingestion_job_id: IngestionJobId | None
    created_at: datetime
    updated_at: datetime

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        project_id: ProjectId,
        source_type: SourceType,
        external_id: str,
        raw_content: RawContent,
        ingestion_job_id: IngestionJobId | None = None,
    ) -> "Document":
        now = datetime.utcnow()
        return cls(
            id=DocumentId(new_id()),
            project_id=project_id,
            source_type=source_type,
            external_id=external_id,
            raw_content=raw_content,
            structured_content=None,
            embedding_vector=None,
            ingestion_job_id=ingestion_job_id,
            created_at=now,
            updated_at=now,
        )

    # ------------------------------------------------------------------
    # Domain behaviour
    # ------------------------------------------------------------------

    def with_structured_content(
        self, structured_content: StructuredContent
    ) -> "Document":
        """Return a new Document with the structured content attached."""
        return Document(
            id=self.id,
            project_id=self.project_id,
            source_type=self.source_type,
            external_id=self.external_id,
            raw_content=self.raw_content,
            structured_content=structured_content,
            embedding_vector=self.embedding_vector,
            ingestion_job_id=self.ingestion_job_id,
            created_at=self.created_at,
            updated_at=datetime.utcnow(),
        )

    def with_embedding(self, vector: EmbeddingVector) -> "Document":
        """Return a new Document with the embedding vector attached."""
        return Document(
            id=self.id,
            project_id=self.project_id,
            source_type=self.source_type,
            external_id=self.external_id,
            raw_content=self.raw_content,
            structured_content=self.structured_content,
            embedding_vector=vector,
            ingestion_job_id=self.ingestion_job_id,
            created_at=self.created_at,
            updated_at=datetime.utcnow(),
        )

    @property
    def is_structured(self) -> bool:
        return self.structured_content is not None

    @property
    def is_embedded(self) -> bool:
        return self.embedding_vector is not None
