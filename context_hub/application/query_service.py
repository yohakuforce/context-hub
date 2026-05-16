"""QueryService — use-case layer for hybrid search.

Wraps embedding + DocumentRepository.hybrid_search into a single call
that API routers and MCP tools can use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from context_hub.domain.document.entities import Document
from context_hub.domain.document.repository import DocumentRepository
from context_hub.infrastructure.embedding.base import EmbeddingProvider
from context_hub.shared.types import ProjectId, SourceType


@dataclass(frozen=True)
class QueryResult:
    """Single search result item."""

    document: Document
    score: float

    @property
    def snippet(self) -> str:
        """Return the first 300 characters of raw text as a snippet."""
        text = self.document.raw_content.text or ""
        return text[:300] + ("..." if len(text) > 300 else "")

    @property
    def title(self) -> str:
        """Derive a display title from structured content or raw text."""
        if self.document.structured_content and self.document.structured_content.summary:
            return self.document.structured_content.summary[:80]
        raw = self.document.raw_content.text or ""
        first_line = raw.split("\n")[0].strip()
        return first_line[:80] if first_line else f"[{self.document.source_type}]"


class QueryService:
    """Executes hybrid search against the document store.

    Args:
        document_repo:      DocumentRepository backed by PostgreSQL+pgvector.
        embedding_provider: EmbeddingProvider for query vectorisation.
    """

    def __init__(
        self,
        document_repo: DocumentRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._document_repo = document_repo
        self._embedding = embedding_provider

    async def search(
        self,
        project_id: ProjectId,
        query: str,
        top_k: int = 5,
        source_types: Optional[list[SourceType]] = None,
    ) -> list[QueryResult]:
        """Embed *query* and run hybrid search.

        Returns:
            List of QueryResult ordered by descending relevance score.
        """
        vector = await self._embedding.embed(query)
        raw_results = await self._document_repo.hybrid_search(
            query_text=query,
            vector=vector,
            project_id=project_id,
            top_k=top_k,
            source_types=source_types,
        )
        return [
            QueryResult(document=doc, score=score)
            for doc, score in raw_results
        ]
