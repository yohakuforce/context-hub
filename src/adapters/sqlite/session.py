"""SQLite connection factory with sqlite-vec extension loading.

Provides a context manager that yields a synchronous sqlite3.Connection
with the sqlite-vec extension pre-loaded and WAL mode enabled.

All async adapters use asyncio.to_thread() to offload blocking I/O,
keeping the event loop unblocked while retaining the synchronous SQLite API.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import sqlite_vec


def _apply_connection_settings(conn: sqlite3.Connection) -> None:
    """Apply per-connection pragmas required by Context-Hub.

    Args:
        conn: Open SQLite connection to configure.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # busy_timeout lets the connection retry on SQLITE_BUSY instead of failing
    # immediately.  30 000 ms matches the connect timeout below.
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row


def load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension into *conn*.

    Must be called before any vec0 virtual table operations.

    Args:
        conn: Open SQLite connection with extension loading enabled.

    Raises:
        RuntimeError: If sqlite-vec fails to load.
    """
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Failed to load sqlite-vec extension: {exc}. "
            "Ensure sqlite-vec is installed: pip install sqlite-vec"
        ) from exc


@contextmanager
def open_connection(db_path: str | Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a SQLite connection with sqlite-vec loaded and pragmas applied.

    Args:
        db_path: Filesystem path to the SQLite database file.
                 Use ":memory:" for in-memory databases (tests only).

    Yields:
        Configured sqlite3.Connection ready for vec0 and FTS5 queries.

    Raises:
        RuntimeError: If sqlite-vec fails to load.
    """
    # Each call to open_connection() creates a new connection that is closed
    # before returning.  Connections are never shared across threads, so
    # check_same_thread (the SQLite3 default of True) is safe and correct.
    # timeout=30 causes Python to retry on SQLITE_BUSY for up to 30 seconds
    # before raising OperationalError; busy_timeout PRAGMA provides the same
    # guarantee at the C-library level.
    #
    # isolation_level=None: enable autocommit mode so that Python never issues
    # an implicit BEGIN.  All transactions are driven explicitly via
    # conn.execute("BEGIN") / conn.execute("COMMIT") in the adapters.  This
    # prevents "cannot start a transaction within a transaction" errors when
    # DDL or seed INSERTs are run inside migration scripts.
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    try:
        load_sqlite_vec(conn)
        _apply_connection_settings(conn)
        yield conn
    finally:
        conn.close()
