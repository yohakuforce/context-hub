"""Tests for core.fts — FullTextSearch Protocol."""

from __future__ import annotations

import pytest

from src.core.fts import FullTextSearch
from src.core.vectorstore import ScoredId


# ---------------------------------------------------------------------------
# Minimal conforming implementation
# ---------------------------------------------------------------------------


class _MinimalFTS:
    async def index(self, doc_id: str, content: str, lang: str) -> None:
        pass

    async def search(self, q: str, k: int, filter=None) -> list[ScoredId]:
        return []

    async def delete(self, doc_id: str) -> None:
        pass


class _MissingDelete:
    async def index(self, doc_id: str, content: str, lang: str) -> None:
        pass

    async def search(self, q: str, k: int, filter=None) -> list[ScoredId]:
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullTextSearchProtocol:
    def test_minimal_implementation_satisfies_protocol(self):
        fts = _MinimalFTS()
        assert isinstance(fts, FullTextSearch)

    def test_missing_method_fails_protocol_check(self):
        fts = _MissingDelete()
        assert not isinstance(fts, FullTextSearch)

    def test_plain_object_fails(self):
        assert not isinstance(object(), FullTextSearch)
