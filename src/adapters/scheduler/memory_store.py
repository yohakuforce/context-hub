"""In-memory APScheduler jobstore adapter.

Uses APScheduler's built-in MemoryJobStore.  No external dependencies
required.  Jobs are lost on process restart — suitable for quickstart
and test environments where persistence is not needed.

This is the default ``SCHEDULER_BACKEND=memory`` implementation.
"""

from __future__ import annotations

import logging

from apscheduler.jobstores.memory import MemoryJobStore as _MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_JOBSTORE_ALIAS = "default"


class MemorySchedulerStore:
    """SchedulerStore backed by APScheduler's in-process MemoryJobStore.

    No external dependencies.  All job state is lost when the process exits.
    Suitable for local quickstart and CI environments.

    Example::

        store = MemorySchedulerStore()
        store.bind(scheduler)
        scheduler.start()
    """

    def bind(self, scheduler: AsyncIOScheduler) -> None:
        """Attach an in-memory jobstore to *scheduler*.

        Args:
            scheduler: The AsyncIOScheduler instance to configure.
        """
        scheduler.add_jobstore(_MemoryJobStore(), alias=_JOBSTORE_ALIAS)
        logger.info("scheduler_store_bound backend=memory")

    async def shutdown(self, graceful: bool = True) -> None:
        """No-op for the memory backend — no resources to release.

        Args:
            graceful: Ignored; included for Protocol compatibility.
        """
        logger.debug("memory_scheduler_store_shutdown graceful=%s", graceful)
