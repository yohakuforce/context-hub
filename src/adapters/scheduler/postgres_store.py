"""PostgreSQL-backed APScheduler jobstore adapter.

Uses APScheduler's SQLAlchemyJobStore with a synchronous psycopg2 URL.
APScheduler's SQLAlchemy jobstore uses a synchronous engine internally
(it runs in a thread pool when called from an async context), so we use
``postgresql+psycopg2`` rather than ``asyncpg``.

Suitable for the ``production`` profile.
"""

from __future__ import annotations

import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)

_JOBSTORE_ALIAS = "default"
_DEFAULT_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/context_hub"


class PostgresSchedulerStore:
    """SchedulerStore backed by APScheduler's SQLAlchemyJobStore (PostgreSQL).

    Uses a synchronous SQLAlchemy engine because APScheduler's jobstore
    implementation is synchronous.  The async event loop is not blocked
    because APScheduler dispatches jobstore I/O in a thread pool.

    Args:
        database_url: Synchronous PostgreSQL SQLAlchemy URL.
                      ``postgresql+psycopg2://user:pass@host:port/db``
                      Defaults to a local development URL.

    Example::

        store = PostgresSchedulerStore(
            database_url="postgresql+psycopg2://user:pass@host/db"
        )
        store.bind(scheduler)
        scheduler.start()
    """

    def __init__(self, database_url: str = _DEFAULT_URL) -> None:
        self._database_url = _normalise_url(database_url)

    def bind(self, scheduler: AsyncIOScheduler) -> None:
        """Attach a PostgreSQL-backed SQLAlchemyJobStore to *scheduler*.

        Args:
            scheduler: The AsyncIOScheduler instance to configure.
        """
        engine = create_engine(self._database_url, pool_pre_ping=True)
        jobstore = SQLAlchemyJobStore(engine=engine)
        scheduler.add_jobstore(jobstore, alias=_JOBSTORE_ALIAS)
        logger.info("scheduler_store_bound backend=postgres")

    async def shutdown(self, graceful: bool = True) -> None:
        """Log shutdown; APScheduler disposes engine resources on scheduler.shutdown().

        Args:
            graceful: When True the caller should have already called
                      ``scheduler.shutdown(wait=True)`` before this method.
        """
        logger.info("postgres_scheduler_store_shutdown graceful=%s", graceful)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _normalise_url(url: str) -> str:
    """Convert various PostgreSQL URL schemes to psycopg2 for APScheduler compatibility.

    APScheduler's SQLAlchemy jobstore requires a synchronous driver.
    Handles the following input schemes:

    - ``postgresql+asyncpg://`` — asyncpg async driver (from main DATABASE_URL)
    - ``postgresql://``         — bare dialect with no driver specified
    - ``postgres://``           — Heroku/Render shorthand (rejected by SQLAlchemy 2.x)

    All are converted to ``postgresql+psycopg2://``.

    Args:
        url: Original database URL string.

    Returns:
        Synchronous-driver URL string suitable for APScheduler's SQLAlchemyJobStore.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url
