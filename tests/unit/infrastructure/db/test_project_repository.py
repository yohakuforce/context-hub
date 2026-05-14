"""Unit tests for PostgresProjectRepository mapping logic.

DB is fully mocked — no PostgreSQL connection needed.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.project.entities import Project, SourceConfig
from src.infrastructure.db.models import ProjectRow
from src.infrastructure.db.project_repository import (
    PostgresProjectRepository,
    _domain_to_row,
    _json_to_source,
    _row_to_domain,
    _sources_to_json,
)
from src.shared.types import ProjectId, SourceType


def _make_project(name: str = "Test Project") -> Project:
    return Project.create(name=name, external_project_id="ext-001")


def _make_project_row(project: Project) -> ProjectRow:
    return ProjectRow(
        id=str(project.id),
        name=project.name,
        external_project_id=project.external_project_id,
        sources=[],
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


class TestDomainToRow:
    def test_basic_conversion(self) -> None:
        project = _make_project()
        row = _domain_to_row(project)
        assert row.id == str(project.id)
        assert row.name == project.name
        assert row.external_project_id == project.external_project_id

    def test_sources_serialised_as_list(self) -> None:
        project = _make_project()
        source = SourceConfig(
            source_type=SourceType.SLACK,
            sync_interval_minutes=30,
            is_enabled=True,
        )
        project_with_source = project.add_source(source)
        row = _domain_to_row(project_with_source)
        assert isinstance(row.sources, list)
        assert len(row.sources) == 1
        assert row.sources[0]["source_type"] == "slack"


class TestRowToDomain:
    def test_basic_conversion(self) -> None:
        project = _make_project()
        row = _make_project_row(project)
        result = _row_to_domain(row)
        assert result.id == project.id
        assert result.name == project.name
        assert result.sources == []

    def test_source_roundtrip(self) -> None:
        project = _make_project()
        source = SourceConfig(
            source_type=SourceType.BACKLOG,
            sync_interval_minutes=60,
            is_enabled=True,
            backlog_project_key="MYPROJ",
        )
        project_with_source = project.add_source(source)
        row = _domain_to_row(project_with_source)
        result = _row_to_domain(row)
        assert len(result.sources) == 1
        assert result.sources[0].source_type == SourceType.BACKLOG
        assert result.sources[0].backlog_project_key == "MYPROJ"


class TestSourcesJson:
    def test_empty_sources(self) -> None:
        assert _sources_to_json([]) == []

    def test_slack_source_serialised(self) -> None:
        source = SourceConfig(
            source_type=SourceType.SLACK,
            sync_interval_minutes=15,
            is_enabled=False,
            channel_ids=("C001", "C002"),
        )
        result = _sources_to_json([source])
        assert result[0]["source_type"] == "slack"
        assert result[0]["is_enabled"] is False
        assert result[0]["channel_ids"] == ["C001", "C002"]


class TestJsonToSource:
    def test_slack_source(self) -> None:
        data = {
            "source_type": "slack",
            "sync_interval_minutes": 15,
            "is_enabled": True,
            "channel_ids": ["C001"],
            "backlog_project_key": None,
            "redmine_project_identifier": None,
        }
        source = _json_to_source(data)
        assert source.source_type == SourceType.SLACK
        assert source.channel_ids == ("C001",)

    def test_missing_optional_fields(self) -> None:
        data = {
            "source_type": "redmine",
            "sync_interval_minutes": 60,
            "is_enabled": True,
        }
        source = _json_to_source(data)
        assert source.source_type == SourceType.REDMINE
        assert source.channel_ids == ()
        assert source.backlog_project_key is None


class TestPostgresProjectRepository:
    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        repo = PostgresProjectRepository(session)
        result = await repo.find_by_id(ProjectId("nonexistent-id"))
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_id_returns_domain_when_found(self) -> None:
        project = _make_project()
        row = _make_project_row(project)
        session = AsyncMock()
        session.get = AsyncMock(return_value=row)
        repo = PostgresProjectRepository(session)
        result = await repo.find_by_id(project.id)
        assert result is not None
        assert result.id == project.id

    @pytest.mark.asyncio
    async def test_delete_does_nothing_when_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        repo = PostgresProjectRepository(session)
        # Should not raise
        await repo.delete(ProjectId("nonexistent"))

    @pytest.mark.asyncio
    async def test_save_new_project_adds_to_session(self) -> None:
        project = _make_project()
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        session.add = MagicMock()
        repo = PostgresProjectRepository(session)
        result = await repo.save(project)
        assert result is project
        session.add.assert_called_once()
