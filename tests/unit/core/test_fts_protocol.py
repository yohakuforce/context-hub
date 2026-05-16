"""Tests for core.fts — FullTextSearch Protocol."""

from __future__ import annotations

from context_hub.core.fts import FullTextSearch
from context_hub.core.vectorstore import ScoredId

# ---------------------------------------------------------------------------
# Minimal conforming implementation
# ---------------------------------------------------------------------------


class _MinimalFTS:
    async def index(
        self, doc_id: str, content: str, lang: str, project_id: str = ""
    ) -> None:
        pass

    async def search(
        self, q: str, k: int, project_id: str = "", filter: object = None
    ) -> list[ScoredId]:
        return []

    async def delete(self, doc_id: str) -> None:
        pass


class _MissingDelete:
    async def index(
        self, doc_id: str, content: str, lang: str, project_id: str = ""
    ) -> None:
        pass

    async def search(
        self, q: str, k: int, project_id: str = "", filter: object = None
    ) -> list[ScoredId]:
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullTextSearchProtocol:
    def test_minimal_implementation_satisfies_protocol(self) -> None:
        fts = _MinimalFTS()
        assert isinstance(fts, FullTextSearch)

    def test_missing_method_fails_protocol_check(self) -> None:
        fts = _MissingDelete()
        assert not isinstance(fts, FullTextSearch)

    def test_plain_object_fails(self) -> None:
        assert not isinstance(object(), FullTextSearch)
