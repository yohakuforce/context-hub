"""B-2: serve-resident periodic source sync registration.

`_register_source_sync_jobs` registers one APScheduler interval job per enabled
external source (Slack / Backlog / Redmine / Gmail) across all projects, so a
running `context-hub serve` keeps every source in sync automatically. These
tests cover the enable toggle, source filtering, and failure isolation —
without touching a real database or scheduler.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_hub.main import _register_source_sync_jobs, _source_sync_enabled
from context_hub.shared.types import SourceType


def _source(source_type: SourceType, interval: int = 15) -> MagicMock:
    sc = MagicMock()
    sc.source_type = source_type
    sc.sync_interval_minutes = interval
    return sc


def _project(pid: str, enabled_sources: list) -> MagicMock:
    p = MagicMock()
    p.id = pid
    p.active_sources.return_value = enabled_sources
    return p


class TestSourceSyncEnabledToggle:
    def test_default_enabled(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CH_SOURCE_SYNC_ENABLED", None)
            assert _source_sync_enabled() is True

    @pytest.mark.parametrize("val", ["false", "0", "no", "off", "FALSE"])
    def test_disabled_values(self, val: str) -> None:
        with patch.dict(os.environ, {"CH_SOURCE_SYNC_ENABLED": val}):
            assert _source_sync_enabled() is False


class TestRegisterSourceSyncJobs:
    @pytest.mark.asyncio
    async def test_registers_one_job_per_enabled_external_source(self) -> None:
        """Slack + Backlog enabled, plus a MEETING source which must be skipped."""
        project = _project(
            "proj-1",
            [
                _source(SourceType.SLACK),
                _source(SourceType.BACKLOG),
                _source(SourceType.MEETING),  # not syncable → skipped
            ],
        )
        scheduler = MagicMock()

        with patch.dict(os.environ, {"CH_SOURCE_SYNC_ENABLED": "true"}), patch(
            "context_hub.main._list_projects_for_sync",
            AsyncMock(return_value=[project]),
        ):
            count = await _register_source_sync_jobs(scheduler)

        assert count == 2
        assert scheduler.add_job.call_count == 2
        job_ids = {c.kwargs["id"] for c in scheduler.add_job.call_args_list}
        assert job_ids == {"sync_proj-1_slack", "sync_proj-1_backlog"}

    @pytest.mark.asyncio
    async def test_disabled_registers_nothing(self) -> None:
        scheduler = MagicMock()
        with patch.dict(os.environ, {"CH_SOURCE_SYNC_ENABLED": "false"}):
            count = await _register_source_sync_jobs(scheduler)
        assert count == 0
        scheduler.add_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_listing_failure_is_isolated(self) -> None:
        """If listing projects fails (no DB / not migrated), register nothing — no raise."""
        scheduler = MagicMock()
        with patch.dict(os.environ, {"CH_SOURCE_SYNC_ENABLED": "true"}), patch(
            "context_hub.main._list_projects_for_sync",
            AsyncMock(side_effect=RuntimeError("no such table: projects")),
        ):
            count = await _register_source_sync_jobs(scheduler)
        assert count == 0
        scheduler.add_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_interval_floor_is_enforced(self) -> None:
        """A tiny sync_interval_minutes is raised to the 5-minute floor."""
        project = _project("proj-1", [_source(SourceType.SLACK, interval=1)])
        scheduler = MagicMock()

        with patch.dict(os.environ, {"CH_SOURCE_SYNC_ENABLED": "true"}), patch(
            "context_hub.main._list_projects_for_sync",
            AsyncMock(return_value=[project]),
        ):
            await _register_source_sync_jobs(scheduler)

        trigger = scheduler.add_job.call_args.kwargs["trigger"]
        # IntervalTrigger stores the interval as a timedelta; floor is 5 minutes.
        assert trigger.interval.total_seconds() == 5 * 60
