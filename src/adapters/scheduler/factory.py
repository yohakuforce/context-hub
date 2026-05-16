"""Factory for SchedulerStore implementations.

Selects the correct backend based on the ``SCHEDULER_BACKEND`` environment
variable (or explicit *backend* argument).  Valid values:

- ``memory``   — MemorySchedulerStore (default, quickstart-safe)
- ``sqlite``   — SQLiteSchedulerStore (personal profile)
- ``postgres`` — PostgresSchedulerStore (production profile)

Environment variables read by each backend:

- sqlite:   ``SCHEDULER_SQLITE_DB`` (path, default ``./data/scheduler.db``)
- postgres: ``SCHEDULER_DATABASE_URL`` → ``DATABASE_URL`` → built-in default
            (priority: explicit arg > SCHEDULER_DATABASE_URL > DATABASE_URL > default)
"""

from __future__ import annotations

import os

from src.core.scheduler_store import SchedulerStore

_VALID_BACKENDS = frozenset({"memory", "sqlite", "postgres"})
_ENV_KEY = "SCHEDULER_BACKEND"
_DEFAULT_BACKEND = "memory"
_DEFAULT_SQLITE_PATH = "./data/scheduler.db"
_DEFAULT_PG_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/context_hub"


def get_scheduler_store(
    backend: str | None = None,
    *,
    sqlite_db_path: str | None = None,
    database_url: str | None = None,
) -> SchedulerStore:
    """Return the SchedulerStore implementation for *backend*.

    The backend is resolved in this order:
    1. Explicit *backend* argument (if provided).
    2. ``SCHEDULER_BACKEND`` environment variable.
    3. ``"memory"`` (default, suitable for quickstart and CI).

    For the **sqlite** backend the DB path is resolved in this order:
    1. Explicit *sqlite_db_path* argument (if provided and not None).
    2. ``SCHEDULER_SQLITE_DB`` environment variable.
    3. ``"./data/scheduler.db"`` (built-in default).

    For the **postgres** backend the connection URL is resolved in this order:
    1. Explicit *database_url* argument (if provided and not None).
    2. ``SCHEDULER_DATABASE_URL`` environment variable (dedicated scheduler DB).
    3. ``DATABASE_URL`` environment variable (shared main DB, auto-converted).
    4. Built-in localhost development URL.

    Args:
        backend:       One of "memory", "sqlite", "postgres", or None to
                       read from the environment.
        sqlite_db_path: Path for the SQLite scheduler database.  Only used
                        when *backend* is ``"sqlite"``.  When None, falls back
                        to the ``SCHEDULER_SQLITE_DB`` env var, then the
                        built-in default.
        database_url:  PostgreSQL connection URL.  Only used when *backend*
                       is ``"postgres"``.  When None, falls back to
                       ``SCHEDULER_DATABASE_URL``, then ``DATABASE_URL``,
                       then the built-in default.

    Returns:
        A SchedulerStore implementation satisfying the Protocol.

    Raises:
        ValueError: If *backend* is not a recognised value.
    """
    resolved = backend or os.environ.get(_ENV_KEY, _DEFAULT_BACKEND)
    if resolved not in _VALID_BACKENDS:
        raise ValueError(
            f"Unknown SCHEDULER_BACKEND {resolved!r}. "
            f"Valid options: {', '.join(sorted(_VALID_BACKENDS))}"
        )

    if resolved == "memory":
        from src.adapters.scheduler.memory_store import MemorySchedulerStore
        return MemorySchedulerStore()

    if resolved == "sqlite":
        effective_path = (
            sqlite_db_path
            or os.environ.get("SCHEDULER_SQLITE_DB", _DEFAULT_SQLITE_PATH)
        )
        from src.adapters.scheduler.sqlite_store import SQLiteSchedulerStore
        return SQLiteSchedulerStore(db_path=effective_path)

    # resolved == "postgres"
    effective_url = (
        database_url
        or os.environ.get("SCHEDULER_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or _DEFAULT_PG_URL
    )
    from src.adapters.scheduler.postgres_store import PostgresSchedulerStore, _normalise_url
    return PostgresSchedulerStore(database_url=_normalise_url(effective_url))
