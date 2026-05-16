"""Unit tests for src/adapters/scheduler/factory.py.

Covers:
- H-2: Postgres branch respects DATABASE_URL / SCHEDULER_DATABASE_URL env vars.
- H-3: SQLite branch respects SCHEDULER_SQLITE_DB env var.
- M-1: SCHEDULER_DATABASE_URL takes priority over DATABASE_URL.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestGetSchedulerStoreMemory:
    """Default 'memory' backend requires no external services."""

    def test_returns_memory_store_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            env = {k: v for k, v in os.environ.items() if k != "SCHEDULER_BACKEND"}
            with patch.dict(os.environ, env, clear=True):
                from context_hub.adapters.scheduler.factory import get_scheduler_store
                from context_hub.adapters.scheduler.memory_store import MemorySchedulerStore

                store = get_scheduler_store()
        assert isinstance(store, MemorySchedulerStore)

    def test_returns_memory_store_when_env_is_memory(self) -> None:
        with patch.dict(os.environ, {"SCHEDULER_BACKEND": "memory"}):
            from context_hub.adapters.scheduler.factory import get_scheduler_store
            from context_hub.adapters.scheduler.memory_store import MemorySchedulerStore

            store = get_scheduler_store()
        assert isinstance(store, MemorySchedulerStore)

    def test_explicit_backend_arg_overrides_env(self) -> None:
        with patch.dict(os.environ, {"SCHEDULER_BACKEND": "postgres"}):
            from context_hub.adapters.scheduler.factory import get_scheduler_store
            from context_hub.adapters.scheduler.memory_store import MemorySchedulerStore

            store = get_scheduler_store(backend="memory")
        assert isinstance(store, MemorySchedulerStore)

    def test_unknown_backend_raises_value_error(self) -> None:
        from context_hub.adapters.scheduler.factory import get_scheduler_store

        with pytest.raises(ValueError, match="Unknown SCHEDULER_BACKEND"):
            get_scheduler_store(backend="redis")


class TestGetSchedulerStoreSQLite:
    """H-3: SQLite backend reads SCHEDULER_SQLITE_DB env var."""

    def test_returns_sqlite_store(self) -> None:
        with patch.dict(os.environ, {"SCHEDULER_BACKEND": "sqlite"}):
            from context_hub.adapters.scheduler.factory import get_scheduler_store
            from context_hub.adapters.scheduler.sqlite_store import SQLiteSchedulerStore

            store = get_scheduler_store()
        assert isinstance(store, SQLiteSchedulerStore)

    def test_scheduler_sqlite_db_env_var_is_respected(self) -> None:
        """H-3: SCHEDULER_SQLITE_DB must control the db_path used."""
        custom_path = "/tmp/test_scheduler_h3.db"
        env = {"SCHEDULER_BACKEND": "sqlite", "SCHEDULER_SQLITE_DB": custom_path}
        with patch.dict(os.environ, env):
            from context_hub.adapters.scheduler.factory import get_scheduler_store
            from context_hub.adapters.scheduler.sqlite_store import SQLiteSchedulerStore

            store = get_scheduler_store()
        assert isinstance(store, SQLiteSchedulerStore)
        assert store._db_path == custom_path  # type: ignore[attr-defined]

    def test_explicit_sqlite_db_path_arg_overrides_env(self) -> None:
        """Explicit sqlite_db_path argument takes priority over SCHEDULER_SQLITE_DB."""
        env = {
            "SCHEDULER_BACKEND": "sqlite",
            "SCHEDULER_SQLITE_DB": "/tmp/from_env.db",
        }
        with patch.dict(os.environ, env):
            from context_hub.adapters.scheduler.factory import get_scheduler_store
            from context_hub.adapters.scheduler.sqlite_store import SQLiteSchedulerStore

            store = get_scheduler_store(sqlite_db_path="/tmp/from_arg.db")
        assert isinstance(store, SQLiteSchedulerStore)
        assert store._db_path == "/tmp/from_arg.db"  # type: ignore[attr-defined]

    def test_default_sqlite_path_when_no_env(self) -> None:
        """Falls back to built-in default when SCHEDULER_SQLITE_DB is not set."""
        env = {"SCHEDULER_BACKEND": "sqlite"}
        env_clean = {k: v for k, v in os.environ.items() if k not in ("SCHEDULER_SQLITE_DB",)}
        env_clean.update(env)
        with patch.dict(os.environ, env_clean, clear=True):
            from context_hub.adapters.scheduler.factory import get_scheduler_store
            from context_hub.adapters.scheduler.sqlite_store import SQLiteSchedulerStore

            store = get_scheduler_store()
        assert isinstance(store, SQLiteSchedulerStore)
        assert store._db_path == "./data/scheduler.db"  # type: ignore[attr-defined]


class TestGetSchedulerStorePostgres:
    """H-2 + M-1: Postgres backend reads DATABASE_URL and SCHEDULER_DATABASE_URL env vars."""

    def _make_postgres_store(self, env: dict[str, str]) -> object:
        """Helper: create a PostgresSchedulerStore with given env vars.

        Patches PostgresSchedulerStore.__init__ to avoid real DB connections.
        """
        with patch.dict(os.environ, env):
            with patch(
                "context_hub.adapters.scheduler.postgres_store.PostgresSchedulerStore.__init__",
                return_value=None,
            ) as mock_init:
                from context_hub.adapters.scheduler.factory import get_scheduler_store
                get_scheduler_store(backend="postgres")
                return mock_init

    def test_database_url_env_var_is_respected(self) -> None:
        """H-2: When SCHEDULER_DATABASE_URL is absent, DATABASE_URL must be used."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@db-host:5432/mydb",
        }
        # Remove SCHEDULER_DATABASE_URL if set
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("SCHEDULER_DATABASE_URL", "DATABASE_URL")}
        clean_env.update(env)

        with patch.dict(os.environ, clean_env, clear=True):
            with patch(
                "context_hub.adapters.scheduler.postgres_store.PostgresSchedulerStore.__init__",
                return_value=None,
            ) as mock_init:
                from context_hub.adapters.scheduler.factory import get_scheduler_store
                get_scheduler_store(backend="postgres")

        # _normalise_url converts asyncpg → psycopg2
        mock_init.assert_called_once_with(
            database_url="postgresql+psycopg2://user:pass@db-host:5432/mydb"
        )

    def test_scheduler_database_url_takes_priority_over_database_url(self) -> None:
        """M-1: SCHEDULER_DATABASE_URL must win over DATABASE_URL."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://shared:pass@shared-host:5432/main",
            "SCHEDULER_DATABASE_URL": "postgresql+psycopg2://sched:pass@sched-host:5432/sched",
        }
        with patch.dict(os.environ, env):
            with patch(
                "context_hub.adapters.scheduler.postgres_store.PostgresSchedulerStore.__init__",
                return_value=None,
            ) as mock_init:
                from context_hub.adapters.scheduler.factory import get_scheduler_store
                get_scheduler_store(backend="postgres")

        mock_init.assert_called_once_with(
            database_url="postgresql+psycopg2://sched:pass@sched-host:5432/sched"
        )

    def test_explicit_database_url_arg_takes_top_priority(self) -> None:
        """Explicit database_url arg must beat all env vars."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://shared:pass@shared-host:5432/main",
            "SCHEDULER_DATABASE_URL": "postgresql+psycopg2://sched:pass@sched-host:5432/sched",
        }
        with patch.dict(os.environ, env):
            with patch(
                "context_hub.adapters.scheduler.postgres_store.PostgresSchedulerStore.__init__",
                return_value=None,
            ) as mock_init:
                from context_hub.adapters.scheduler.factory import get_scheduler_store
                get_scheduler_store(
                    backend="postgres",
                    database_url="postgresql+psycopg2://explicit:pass@explicit-host:5432/db",
                )

        mock_init.assert_called_once_with(
            database_url="postgresql+psycopg2://explicit:pass@explicit-host:5432/db"
        )

    def test_falls_back_to_default_when_no_db_env_vars(self) -> None:
        """When no DB env vars are set, the built-in localhost default is used."""
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("DATABASE_URL", "SCHEDULER_DATABASE_URL")}
        with patch.dict(os.environ, clean_env, clear=True):
            with patch(
                "context_hub.adapters.scheduler.postgres_store.PostgresSchedulerStore.__init__",
                return_value=None,
            ) as mock_init:
                from context_hub.adapters.scheduler.factory import get_scheduler_store
                get_scheduler_store(backend="postgres")

        mock_init.assert_called_once_with(
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/context_hub"
        )
