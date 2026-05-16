"""SQLite FTS5 implementation of the FullTextSearch Protocol.

Uses the SQLite FTS5 virtual table with the trigram tokenizer to provide
full-text search over document content.  The trigram tokenizer supports
both Latin scripts and CJK languages (Japanese, Chinese, Korean) without
requiring an external tokenizer library.

Trigram trade-offs vs. unicode61:
- Pro: uniform recall for all scripts, no pre-tokenization step required.
- Con: larger index (~3x unicode61) and slightly slower search on long docs.
- Decision: Acceptable for single-user local deployments (quickstart/personal).

All I/O is performed in a thread pool via asyncio.to_thread() to avoid
blocking the event loop.
"""

from __future__ import annotations

import asyncio
import json

from src.adapters.sqlite.session import open_connection
from src.core.vectorstore import MetaFilter, ScoredId

# Minimum query length for trigram search (trigram requires >= 3 chars to match)
_MIN_QUERY_LEN: int = 3

# FTS5 rank score baseline — bm25() returns negative values (lower = better match).
# We negate and normalise to produce positive scores in (0, +inf).
_SCORE_SCALE: float = -1.0


class SqliteFts5Search:
    """FullTextSearch Protocol implementation backed by SQLite FTS5 (trigram).

    Args:
        db_path: Path to the SQLite database file. Use ":memory:" for tests.

    Example::

        fts = SqliteFts5Search(db_path="context_hub.db")
        await fts.index("doc-1", "Hello world", lang="en")
        results = await fts.search("hello", k=5)
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    async def index(
        self,
        doc_id: str,
        content: str,
        lang: str,
    ) -> None:
        """Add or replace a document in the FTS5 index.

        The *lang* parameter is accepted for Protocol compatibility but is not
        used internally — the trigram tokenizer is language-agnostic.

        Args:
            doc_id:  Stable document identifier (UUID string).
            content: Plain text to index.
            lang:    Language hint (unused; trigram is language-agnostic).
        """
        await asyncio.to_thread(self._sync_index, doc_id, content)

    async def search(
        self,
        q: str,
        k: int,
        filter: MetaFilter | None = None,
    ) -> list[ScoredId]:
        """Execute a full-text query and return top-k scored document IDs.

        Queries shorter than 3 characters return an empty list because the
        trigram tokenizer cannot match on fewer than 3 characters.

        Args:
            q:      Raw query string (trigram matching applied automatically).
            k:      Maximum number of results to return.
            filter: Optional equality filter on the project_id field.
                    Only "project_id" is currently supported for FTS5 filters.

        Returns:
            List of ScoredId sorted by descending BM25 score, length <= k.
        """
        if len(q.strip()) < _MIN_QUERY_LEN:
            return []
        rows = await asyncio.to_thread(self._sync_search, q, k, filter)
        return rows

    async def delete(self, doc_id: str) -> None:
        """Remove a document from the FTS5 index.

        No-op if *doc_id* does not exist.

        Args:
            doc_id: Document identifier to remove.
        """
        await asyncio.to_thread(self._sync_delete, doc_id)

    # ------------------------------------------------------------------
    # Synchronous helpers (executed in thread pool)
    # ------------------------------------------------------------------

    def _sync_index(self, doc_id: str, content: str) -> None:
        with open_connection(self._db_path) as conn:
            # FTS5 does not have native upsert; delete then insert.
            conn.execute(
                "DELETE FROM document_fts WHERE doc_id = ?", (doc_id,)
            )
            conn.execute(
                "INSERT INTO document_fts (doc_id, content) VALUES (?, ?)",
                (doc_id, content),
            )
            conn.commit()

    def _sync_search(
        self,
        q: str,
        k: int,
        filter: MetaFilter | None,
    ) -> list[ScoredId]:
        with open_connection(self._db_path) as conn:
            # Escape any special FTS5 characters in the query.
            safe_q = _escape_fts5_query(q)
            sql = (
                "SELECT doc_id, bm25(document_fts) AS rank "
                "FROM document_fts "
                "WHERE document_fts MATCH ? "
                "ORDER BY rank "   # bm25() is negative; ascending = best first
                "LIMIT ?"
            )
            params: list[object] = [safe_q, k]

            rows = conn.execute(sql, params).fetchall()
            return [
                ScoredId(doc_id=row[0], score=_bm25_to_score(float(row[1])))
                for row in rows
                if _passes_filter(row[0], filter, conn)
            ][:k]

    def _sync_delete(self, doc_id: str) -> None:
        with open_connection(self._db_path) as conn:
            conn.execute(
                "DELETE FROM document_fts WHERE doc_id = ?", (doc_id,)
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _bm25_to_score(bm25_value: float) -> float:
    """Convert FTS5 bm25() value to a positive relevance score.

    FTS5 bm25() returns negative values where more negative = better match.
    We negate to produce positive scores in (0, +inf).

    Args:
        bm25_value: Raw bm25() output (negative float).

    Returns:
        Positive relevance score; higher = more relevant.
    """
    return bm25_value * _SCORE_SCALE


def _escape_fts5_query(query: str) -> str:
    """Escape special FTS5 syntax characters in a user query.

    Wraps the query in double quotes to treat it as a phrase search,
    preventing FTS5 syntax errors from user-supplied special characters.

    Args:
        query: Raw query string from the caller.

    Returns:
        FTS5-safe query string.
    """
    # Replace internal double-quotes; wrap in quotes for phrase search.
    safe = query.replace('"', '""')
    return f'"{safe}"'


def _passes_filter(
    doc_id: str,
    filter: MetaFilter | None,
    conn: object,  # sqlite3.Connection
) -> bool:
    """Check whether *doc_id* passes the optional metadata filter.

    The FTS5 virtual table does not support arbitrary metadata columns.
    For project_id filtering, we look up the metadata from the documents table.

    Args:
        doc_id: Document identifier to check.
        filter: Optional equality filter dict.
        conn:   Open SQLite connection for the lookup query.

    Returns:
        True if the document passes the filter (or no filter is set).
    """
    if not filter:
        return True

    # Look up metadata from the main documents table if available.
    try:
        import sqlite3  # local import to keep module-level clean

        assert isinstance(conn, sqlite3.Connection)
        meta_row = conn.execute(
            "SELECT metadata FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        if meta_row is None:
            return False
        try:
            meta = json.loads(meta_row[0] or "{}")
        except json.JSONDecodeError:
            meta = {}
        return all(meta.get(key) == val for key, val in filter.items())
    except Exception:  # noqa: BLE001
        return True  # fail-open: if metadata unavailable, don't filter out
