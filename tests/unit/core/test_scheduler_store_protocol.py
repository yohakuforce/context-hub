"""Unit tests for the SchedulerStore Protocol.

Verifies:
- The Protocol is @runtime_checkable.
- MemorySchedulerStore, SQLiteSchedulerStore satisfy the Protocol.
- PostgresSchedulerStore satisfies the Protocol (import-only check).
- SchedulerStore factory resolves the correct implementation.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.core.scheduler_store import SchedulerStore


# ---------------------------------------------------------------------------
# Protocol runtime_checkable tests
# ---------------------------------------------------------------------------


class TestSchedulerStoreProtocol:
    def test_is_runtime_checkable(self) -> None:
        """Protocol must support isinstance() checks at runtime."""
        from src.adapters.scheduler.memory_store import MemorySchedulerStore

        store = MemorySchedulerStore()
        assert isinstance(store, SchedulerStore)

    def test_rejects_non_conforming_object(self) -> None:
        """Plain object without bind/shutdown must not satisfy the Protocol."""
        assert not isinstance(object(), SchedulerStore)

    def test_rejects_partial_conformance(self) -> None:
        """Object missing shutdown must not satisfy the Protocol."""

        class OnlyBind:
            def bind(self, scheduler) -> None:  # type: ignore[no-untyped-def]
                pass

        assert not isinstance(OnlyBind(), SchedulerStore)


# ---------------------------------------------------------------------------
# MemorySchedulerStore tests
# ---------------------------------------------------------------------------


class TestMemorySchedulerStore:
    def test_bind_adds_memory_jobstore(self) -> None:
        """bind() should add a jobstore to the scheduler."""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        from src.adapters.scheduler.memory_store import MemorySchedulerStore

        store = MemorySchedulerStore()
        scheduler = AsyncIOScheduler()
        store.bind(scheduler)
        # APScheduler stores jobstores in _jobstores dict
        assert "default" in scheduler._jobstores  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_shutdown_is_noop(self) -> None:
        """shutdown() must complete without raising for the memory backend."""
        from src.adapters.scheduler.memory_store import MemorySchedulerStore

        store = MemorySchedulerStore()
        # Should not raise
        await store.shutdown(graceful=True)
        await store.shutdown(graceful=False)

    def test_satisfies_protocol(self) -> None:
        """MemorySchedulerStore must satisfy SchedulerStore Protocol."""
        from src.adapters.scheduler.memory_store import MemorySchedulerStore

        store = MemorySchedulerStore()
        assert isinstance(store, SchedulerStore)


# ---------------------------------------------------------------------------
# SQLiteSchedulerStore tests
# ---------------------------------------------------------------------------


class TestSQLiteSchedulerStore:
    def test_satisfies_protocol(self) -> None:
        """SQLiteSchedulerStore must satisfy SchedulerStore Protocol."""
        from src.adapters.scheduler.sqlite_store import SQLiteSchedulerStore

        store = SQLiteSchedulerStore(db_path=":memory:")
        assert isinstance(store, SchedulerStore)

    def test_bind_adds_sqlalchemy_jobstore(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """bind() should configure a SQLAlchemyJobStore on the scheduler."""
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        from src.adapters.scheduler.sqlite_store import SQLiteSchedulerStore

        db = tmp_path / "scheduler_test.db"
        store = SQLiteSchedulerStore(db_path=str(db))
        scheduler = AsyncIOScheduler()
        store.bind(scheduler)
        assert "default" in scheduler._jobstores  # type: ignore[attr-defined]
        assert isinstance(scheduler._jobstores["default"], SQLAlchemyJobStore)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_shutdown_does_not_raise(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """shutdown() must not raise for the SQLite backend."""
        from src.adapters.scheduler.sqlite_store import SQLiteSchedulerStore

        store = SQLiteSchedulerStore(db_path=str(tmp_path / "sched.db"))
        await store.shutdown(graceful=True)


# ---------------------------------------------------------------------------
# PostgresSchedulerStore tests (import + protocol only; no live DB)
# ---------------------------------------------------------------------------


class TestPostgresSchedulerStore:
    def test_satisfies_protocol(self) -> None:
        """PostgresSchedulerStore must satisfy SchedulerStore Protocol."""
        from src.adapters.scheduler.postgres_store import PostgresSchedulerStore

        store = PostgresSchedulerStore(
            database_url="postgresql+psycopg2://user:pass@localhost/db"
        )
        assert isinstance(store, SchedulerStore)

    def test_normalises_asyncpg_url(self) -> None:
        """asyncpg URL should be converted to psycopg2 URL automatically."""
        from src.adapters.scheduler.postgres_store import PostgresSchedulerStore

        store = PostgresSchedulerStore(
            database_url="postgresql+asyncpg://user:pass@localhost/db"
        )
        assert "psycopg2" in store._database_url
        assert "asyncpg" not in store._database_url

    @pytest.mark.asyncio
    async def test_shutdown_does_not_raise(self) -> None:
        """shutdown() must not raise for the Postgres backend."""
        from src.adapters.scheduler.postgres_store import PostgresSchedulerStore

        store = PostgresSchedulerStore(
            database_url="postgresql+psycopg2://user:pass@localhost/db"
        )
        await store.shutdown(graceful=True)


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestGetSchedulerStoreFactory:
    def test_default_is_memory(self) -> None:
        """Without explicit backend, factory returns MemorySchedulerStore."""
        from src.adapters.scheduler.factory import get_scheduler_store
        from src.adapters.scheduler.memory_store import MemorySchedulerStore

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SCHEDULER_BACKEND", None)
            store = get_scheduler_store()
        assert isinstance(store, MemorySchedulerStore)

    def test_explicit_memory(self) -> None:
        """Explicit 'memory' backend returns MemorySchedulerStore."""
        from src.adapters.scheduler.factory import get_scheduler_store
        from src.adapters.scheduler.memory_store import MemorySchedulerStore

        store = get_scheduler_store(backend="memory")
        assert isinstance(store, MemorySchedulerStore)

    def test_explicit_sqlite(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Explicit 'sqlite' backend returns SQLiteSchedulerStore."""
        from src.adapters.scheduler.factory import get_scheduler_store
        from src.adapters.scheduler.sqlite_store import SQLiteSchedulerStore

        store = get_scheduler_store(
            backend="sqlite",
            sqlite_db_path=str(tmp_path / "sched.db"),
        )
        assert isinstance(store, SQLiteSchedulerStore)

    def test_explicit_postgres(self) -> None:
        """Explicit 'postgres' backend returns PostgresSchedulerStore."""
        from src.adapters.scheduler.factory import get_scheduler_store
        from src.adapters.scheduler.postgres_store import PostgresSchedulerStore

        store = get_scheduler_store(
            backend="postgres",
            database_url="postgresql+psycopg2://u:p@localhost/db",
        )
        assert isinstance(store, PostgresSchedulerStore)

    def test_env_var_selects_backend(self) -> None:
        """SCHEDULER_BACKEND env var should be respected."""
        from src.adapters.scheduler.factory import get_scheduler_store
        from src.adapters.scheduler.memory_store import MemorySchedulerStore

        with patch.dict(os.environ, {"SCHEDULER_BACKEND": "memory"}):
            store = get_scheduler_store()
        assert isinstance(store, MemorySchedulerStore)

    def test_unknown_backend_raises(self) -> None:
        """Unknown backend value should raise ValueError."""
        from src.adapters.scheduler.factory import get_scheduler_store

        with pytest.raises(ValueError, match="Unknown SCHEDULER_BACKEND"):
            get_scheduler_store(backend="invalid")

    def test_env_var_unknown_raises(self) -> None:
        """Unknown SCHEDULER_BACKEND env var should raise ValueError."""
        from src.adapters.scheduler.factory import get_scheduler_store

        with patch.dict(os.environ, {"SCHEDULER_BACKEND": "redis"}):
            with pytest.raises(ValueError, match="Unknown SCHEDULER_BACKEND"):
                get_scheduler_store()
