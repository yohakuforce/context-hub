"""FullTextSearch Protocol — backend-agnostic full-text index abstraction.

Implementations include:
- PostgreSQL tsvector / plainto_tsquery  (Phase 1)
- SQLite FTS5                            (Phase 2)

Design notes:
- Lang is a simple string alias (e.g. "ja", "en") to keep the interface
  dependency-free.  Adapters map it to backend-specific language configs.
- MetaFilter is imported from core.vectorstore to avoid duplication.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from context_hub.core.vectorstore import MetaFilter, ScoredId

# Language identifier (BCP-47 language tag or backend-specific alias).
Lang = str


@runtime_checkable
class FullTextSearch(Protocol):
    """Structural interface for full-text search backends.

    The Protocol is @runtime_checkable so isinstance checks work in tests.
    """

    async def index(
        self,
        doc_id: str,
        content: str,
        lang: Lang,
        project_id: str = "",
    ) -> None:
        """Add or update a document in the full-text index.

        Args:
            doc_id:     Stable document identifier (UUID string).
            content:    Plain text to index (pre-processed by the caller).
            lang:       Language hint for tokenisation / stemming.
            project_id: Project scope stored alongside each FTS row so that
                        search() can enforce tenant isolation without a JOIN.
                        Defaults to "" for single-tenant / legacy callers.
        """
        ...

    async def search(
        self,
        q: str,
        k: int,
        project_id: str,
        filter: MetaFilter | None = None,
    ) -> list[ScoredId]:
        """Execute a full-text query and return top-k scored document IDs.

        project_id is mandatory to enforce multi-tenant isolation: each
        implementation must restrict results to documents belonging to the
        specified project, preventing cross-project data leakage.

        Args:
            q:          Raw query string (the adapter handles tokenisation).
            k:          Maximum number of results.
            project_id: Project scope; implementations MUST filter by this value.
            filter:     Optional metadata filter (same semantics as VectorStore).

        Returns:
            List of ScoredId sorted by descending score, length <= k.
        """
        ...

    async def delete(self, doc_id: str) -> None:
        """Remove a document from the full-text index.

        No-op if *doc_id* does not exist.
        """
        ...
