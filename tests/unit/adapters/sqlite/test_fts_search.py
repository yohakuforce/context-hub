"""Tests for SqliteFts5Search — FullTextSearch Protocol implementation.

Covers:
- index + search basic flow
- delete removes document from FTS index
- short queries (< 3 chars) return empty list
- BM25 scores are positive
- Protocol isinstance check
- Japanese trigram search
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlite_vec

from context_hub.adapters.sqlite.fts_search import SqliteFts5Search
from context_hub.core.fts import FullTextSearch


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Return a path to an initialised SQLite database with schema applied."""
    path = str(tmp_path / "fts_test.db")
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    schema_path = (
        Path(__file__).parent.parent.parent.parent.parent
        / "context_hub" / "_sqlite_schema" / "001_init.sql"
    )
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.close()
    return path


_TEST_PROJECT_ID = "test-project-001"
_OTHER_PROJECT_ID = "other-project-002"


@pytest.mark.asyncio
class TestSqliteFts5Search:
    async def test_index_and_search_returns_result(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-1", "hello world test content",
            lang="en", project_id=_TEST_PROJECT_ID,
        )
        results = await fts.search("hello", k=5, project_id=_TEST_PROJECT_ID)
        assert len(results) == 1
        assert results[0].doc_id == "doc-1"

    async def test_search_score_is_positive(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-1", "artificial intelligence machine learning",
            lang="en", project_id=_TEST_PROJECT_ID,
        )
        results = await fts.search("intelligence", k=5, project_id=_TEST_PROJECT_ID)
        assert all(r.score > 0 for r in results)

    async def test_search_respects_k_limit(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        for i in range(5):
            await fts.index(
                f"doc-{i}", f"search term content document {i}",
                lang="en", project_id=_TEST_PROJECT_ID,
            )
        results = await fts.search(
            "search term content", k=2, project_id=_TEST_PROJECT_ID
        )
        assert len(results) <= 2

    async def test_delete_removes_document(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-to-delete", "unique phrase for deletion testing",
            lang="en", project_id=_TEST_PROJECT_ID,
        )
        await fts.delete("doc-to-delete")
        results = await fts.search("unique phrase", k=5, project_id=_TEST_PROJECT_ID)
        ids = [r.doc_id for r in results]
        assert "doc-to-delete" not in ids

    async def test_delete_nonexistent_is_noop(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        await fts.delete("nonexistent-doc")  # must not raise

    async def test_short_query_returns_empty(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-1", "hello world", lang="en", project_id=_TEST_PROJECT_ID
        )
        # 2 characters — below trigram minimum
        results = await fts.search("hi", k=5, project_id=_TEST_PROJECT_ID)
        assert results == []

    async def test_single_char_query_returns_empty(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-1", "hello world", lang="en", project_id=_TEST_PROJECT_ID
        )
        results = await fts.search("h", k=5, project_id=_TEST_PROJECT_ID)
        assert results == []

    async def test_upsert_replaces_existing_content(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-1", "original content text", lang="en", project_id=_TEST_PROJECT_ID
        )
        await fts.index(
            "doc-1", "completely different words here",
            lang="en", project_id=_TEST_PROJECT_ID,
        )
        # "original" should not appear in new content
        results = await fts.search(
            "completely different", k=5, project_id=_TEST_PROJECT_ID
        )
        ids = [r.doc_id for r in results]
        assert "doc-1" in ids

    async def test_empty_index_returns_empty(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        results = await fts.search("anything", k=5, project_id=_TEST_PROJECT_ID)
        assert results == []

    async def test_multiple_documents_ranked(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        # doc-1 mentions "python" more times — should rank higher
        await fts.index(
            "doc-1", "python python python programming language",
            lang="en", project_id=_TEST_PROJECT_ID,
        )
        await fts.index(
            "doc-2", "java programming language",
            lang="en", project_id=_TEST_PROJECT_ID,
        )
        results = await fts.search("python", k=5, project_id=_TEST_PROJECT_ID)
        assert len(results) >= 1
        assert results[0].doc_id == "doc-1"

    async def test_japanese_trigram_search(self, db_path: str) -> None:
        """Trigram tokenizer must handle Japanese text without error."""
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-ja",
            "人工知能と機械学習は現代技術の重要な分野です",
            lang="ja",
            project_id=_TEST_PROJECT_ID,
        )
        # Trigram requires minimum 3 characters; Japanese chars each count as one token
        results = await fts.search("機械学習", k=5, project_id=_TEST_PROJECT_ID)
        # Result may be present (trigram match); verify no exception is raised.
        assert isinstance(results, list)

    async def test_lang_parameter_does_not_raise(self, db_path: str) -> None:
        """lang parameter is accepted for Protocol compat but not required for search."""
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-1", "language parameter test content",
            lang="fr", project_id=_TEST_PROJECT_ID,
        )
        results = await fts.search("language", k=5, project_id=_TEST_PROJECT_ID)
        assert len(results) == 1

    async def test_satisfies_full_text_search_protocol(self, db_path: str) -> None:
        fts = SqliteFts5Search(db_path)
        assert isinstance(fts, FullTextSearch)

    async def test_special_fts5_chars_do_not_raise(self, db_path: str) -> None:
        """Queries with FTS5 special characters are safely escaped."""
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-1", "test content with special chars here",
            lang="en", project_id=_TEST_PROJECT_ID,
        )
        # These chars would break raw FTS5 queries
        results = await fts.search('test "content"', k=5, project_id=_TEST_PROJECT_ID)
        assert isinstance(results, list)

    async def test_project_id_isolation(self, db_path: str) -> None:
        """Documents from another project must not appear in search results."""
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-a", "unique isolation test content here",
            lang="en", project_id=_TEST_PROJECT_ID,
        )
        await fts.index(
            "doc-b", "unique isolation test content here",
            lang="en", project_id=_OTHER_PROJECT_ID,
        )
        results = await fts.search(
            "unique isolation", k=10, project_id=_TEST_PROJECT_ID
        )
        ids = [r.doc_id for r in results]
        assert "doc-a" in ids
        assert "doc-b" not in ids

    async def test_k_capped_at_max_k(self, db_path: str) -> None:
        """Passing k > _MAX_K must not raise and must return at most _MAX_K results."""
        from context_hub.adapters.sqlite.fts_search import _MAX_K
        fts = SqliteFts5Search(db_path)
        await fts.index(
            "doc-1", "overflow limit test content here",
            lang="en", project_id=_TEST_PROJECT_ID,
        )
        # Pass k far above _MAX_K; must not raise and must return <= _MAX_K results.
        results = await fts.search(
            "overflow limit test", k=_MAX_K + 9999, project_id=_TEST_PROJECT_ID
        )
        assert len(results) <= _MAX_K
