"""SQLite-backed APScheduler jobstore adapter.

Uses APScheduler's SQLAlchemyJobStore with a SQLite URL.  WAL journal mode
is enforced at connection time to allow concurrent readers without blocking
the writer — important for in-process scheduler + API server cohabitation.

Suitable for the ``personal`` profile (single-user, no Postgres required).
"""

from __future__ import annotations

import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import Engine, create_engine, event

logger = logging.getLogger(__name__)

_JOBSTORE_ALIAS = "default"
_DEFAULT_DB_PATH = "./data/scheduler.db"


class SQLiteSchedulerStore:
    """SchedulerStore backed by APScheduler's SQLAlchemyJobStore (SQLite).

    WAL journal mode is enforced via a SQLAlchemy ``connect`` event so that
    reads do not block the scheduler write path.

    Args:
        db_path: Filesystem path for the SQLite database file.
                 Defaults to ``./data/scheduler.db``.

    Example::

        store = SQLiteSchedulerStore(db_path="./data/scheduler.db")
        store.bind(scheduler)
        scheduler.start()
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._url = f"sqlite:///{db_path}"

    def bind(self, scheduler: AsyncIOScheduler) -> None:
        """Attach a SQLite-backed SQLAlchemyJobStore to *scheduler*.

        WAL mode is enabled on the underlying SQLite connection before the
        jobstore is configured to ensure the pragma takes effect.

        Args:
            scheduler: The AsyncIOScheduler instance to configure.
        """
        engine = create_engine(self._url, connect_args={"check_same_thread": False})
        _enforce_wal_mode(engine)
        jobstore = SQLAlchemyJobStore(engine=engine)
        scheduler.add_jobstore(jobstore, alias=_JOBSTORE_ALIAS)
        logger.info("scheduler_store_bound backend=sqlite db_path=%s", self._db_path)

    async def shutdown(self, graceful: bool = True) -> None:
        """Log shutdown; APScheduler disposes engine resources on scheduler.shutdown().

        Args:
            graceful: When True the caller should have already called
                      ``scheduler.shutdown(wait=True)`` before this method.
        """
        logger.info("sqlite_scheduler_store_shutdown graceful=%s", graceful)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _enforce_wal_mode(engine: Engine) -> None:
    """Register a SQLAlchemy engine event to set WAL journal mode on connect.

    Args:
        engine: SQLAlchemy Engine to patch.
    """

    @event.listens_for(engine, "connect")
    def set_wal_mode(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
