"""Factory for SchedulerStore implementations.

Selects the correct backend based on the ``SCHEDULER_BACKEND`` environment
variable (or explicit *backend* argument).  Valid values:

- ``memory``   — MemorySchedulerStore (default, quickstart-safe)
- ``sqlite``   — SQLiteSchedulerStore (personal profile)
- ``postgres`` — PostgresSchedulerStore (production profile)
"""

from __future__ import annotations

import os

from src.core.scheduler_store import SchedulerStore

_VALID_BACKENDS = frozenset({"memory", "sqlite", "postgres"})
_ENV_KEY = "SCHEDULER_BACKEND"
_DEFAULT_BACKEND = "memory"


def get_scheduler_store(
    backend: str | None = None,
    *,
    sqlite_db_path: str = "./data/scheduler.db",
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/context_hub",
) -> SchedulerStore:
    """Return the SchedulerStore implementation for *backend*.

    The backend is resolved in this order:
    1. Explicit *backend* argument (if provided).
    2. ``SCHEDULER_BACKEND`` environment variable.
    3. ``"memory"`` (default, suitable for quickstart and CI).

    Args:
        backend:       One of "memory", "sqlite", "postgres", or None to
                       read from the environment.
        sqlite_db_path: Path for the SQLite scheduler database.  Only used
                        when *backend* is ``"sqlite"``.
        database_url:  PostgreSQL connection URL.  Only used when *backend*
                       is ``"postgres"``.

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
        from src.adapters.scheduler.sqlite_store import SQLiteSchedulerStore
        return SQLiteSchedulerStore(db_path=sqlite_db_path)

    # resolved == "postgres"
    from src.adapters.scheduler.postgres_store import PostgresSchedulerStore
    return PostgresSchedulerStore(database_url=database_url)
