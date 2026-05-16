"""SchedulerStore Protocol — backend-agnostic APScheduler jobstore abstraction.

Any jobstore backend (in-memory, SQLite, PostgreSQL) that satisfies this
Protocol can be used by the scheduler layer without code changes.

Design notes:
- Uses typing.Protocol (structural subtyping); implementations do NOT need
  to inherit from this class.
- ``bind`` is synchronous because APScheduler jobstore configuration happens
  before the event loop processes requests.
- ``shutdown`` is async to allow graceful drain of running jobs.
- The Protocol is @runtime_checkable so isinstance() checks work in tests.

ADR-002: SchedulerStore abstraction for SCHEDULER_BACKEND env-var driven
         jobstore selection.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from apscheduler.schedulers.asyncio import AsyncIOScheduler


@runtime_checkable
class SchedulerStore(Protocol):
    """Structural interface for APScheduler jobstore backends.

    Implementations configure and lifecycle-manage a single APScheduler
    jobstore.  The scheduler itself is created externally and passed into
    ``bind`` so that tests can inject a fresh scheduler per-test.
    """

    def bind(self, scheduler: AsyncIOScheduler) -> None:
        """Attach the jobstore to *scheduler* and configure it.

        Called once during application startup, before ``scheduler.start()``.
        Implementations should add their jobstore to the scheduler's
        ``jobstores`` configuration.

        Args:
            scheduler: The AsyncIOScheduler instance to configure.
        """
        ...

    async def shutdown(self, graceful: bool = True) -> None:
        """Perform any cleanup needed when the application shuts down.

        For persistent backends (SQLite, PostgreSQL) this may include
        flushing pending writes and closing connections.  For the in-memory
        backend this is a no-op.

        Args:
            graceful: When True, wait for running jobs to complete before
                      returning.  When False, cancel immediately.
        """
        ...
