"""Unit tests for the scheduler module."""

from __future__ import annotations

import pytest

from context_hub.scheduler import get_scheduler, _build_adapter
from context_hub.shared.types import SourceType


class MockSourceConfig:
    def __init__(self, source_type, channel_ids=(), backlog_project_key=None,
                 redmine_project_identifier=None):
        self.source_type = source_type
        self.channel_ids = channel_ids
        self.backlog_project_key = backlog_project_key
        self.redmine_project_identifier = redmine_project_identifier


class TestGetScheduler:
    def test_returns_scheduler_instance(self):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = get_scheduler()
        assert isinstance(scheduler, AsyncIOScheduler)

    def test_returns_same_instance(self):
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()
        assert scheduler1 is scheduler2


class TestBuildAdapter:
    def test_build_slack_adapter(self):
        source = MockSourceConfig(
            source_type=SourceType.SLACK,
            channel_ids=["C001", "C002"],
        )
        adapter = _build_adapter(source, "mock")
        assert adapter is not None
        assert adapter.source_type == SourceType.SLACK

    def test_build_backlog_adapter(self):
        source = MockSourceConfig(
            source_type=SourceType.BACKLOG,
            backlog_project_key="PROJ",
        )
        adapter = _build_adapter(source, "mock")
        assert adapter is not None
        assert adapter.source_type == SourceType.BACKLOG

    def test_build_redmine_adapter(self):
        source = MockSourceConfig(
            source_type=SourceType.REDMINE,
            redmine_project_identifier="proj-id",
        )
        adapter = _build_adapter(source, "mock")
        assert adapter is not None
        assert adapter.source_type == SourceType.REDMINE

    def test_build_unknown_source_returns_none(self):
        source = MockSourceConfig(source_type=SourceType.MEETING)
        adapter = _build_adapter(source, "mock")
        assert adapter is None

    def test_build_adapter_mock_mode(self):
        source = MockSourceConfig(
            source_type=SourceType.SLACK,
            channel_ids=["C001"],
        )
        adapter = _build_adapter(source, "mock")
        assert adapter._ingest_mode == "mock"  # type: ignore[attr-defined]
