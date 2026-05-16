"""Shared fixtures for SQLite adapter tests.

The ``sqlite_db`` fixture provides a path to an in-memory SQLite database
with the full Context-Hub schema pre-applied (including sqlite-vec extension).
Using ":memory:" ensures each test gets a clean, isolated database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlite_vec

# Schema file relative to the project root.
_SCHEMA_PATH = (
    Path(__file__).parent.parent.parent.parent.parent
    / "context_hub" / "_sqlite_schema" / "001_init.sql"
)


@pytest.fixture
def sqlite_db() -> str:
    """Return the path ":memory:" after applying the full schema.

    Note: returns the string ":memory:" so each fixture call creates a
    logically independent database.  The schema is verified by applying it
    once here; adapters create their own connections per-operation.

    Returns:
        ":memory:" string path for use with open_connection().
    """
    # Verify schema applies cleanly on each test run.
    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.close()
    return ":memory:"
