"""Unit tests for Project aggregate (TDD — RED → GREEN)."""

import pytest
from datetime import datetime

from src.domain.project.entities import Project, SourceConfig, EncryptedCredentials
from src.shared.types import SourceType


class TestProjectCreate:
    def test_create_returns_project_with_generated_id(self):
        project = Project.create(name="Test Project")

        assert project.id is not None
        assert project.name == "Test Project"
        assert project.sources == []
        assert isinstance(project.created_at, datetime)

    def test_create_with_external_id(self):
        project = Project.create(name="P", external_project_id="EXT-123")

        assert project.external_project_id == "EXT-123"

    def test_two_projects_have_different_ids(self):
        p1 = Project.create(name="A")
        p2 = Project.create(name="B")

        assert p1.id != p2.id


class TestProjectAddSource:
    def _make_config(self, source_type: SourceType) -> SourceConfig:
        return SourceConfig(
            source_type=source_type,
            sync_interval_minutes=15,
            is_enabled=True,
        )

    def test_add_source_returns_new_project_with_source(self):
        project = Project.create(name="P")
        config = self._make_config(SourceType.SLACK)

        updated = project.add_source(config)

        assert len(updated.sources) == 1
        assert updated.sources[0].source_type == SourceType.SLACK

    def test_add_source_does_not_mutate_original(self):
        project = Project.create(name="P")
        config = self._make_config(SourceType.SLACK)

        project.add_source(config)

        assert len(project.sources) == 0

    def test_add_duplicate_source_raises(self):
        project = Project.create(name="P")
        config = self._make_config(SourceType.SLACK)
        project = project.add_source(config)

        with pytest.raises(ValueError, match="already configured"):
            project.add_source(config)

    def test_add_multiple_different_sources(self):
        project = Project.create(name="P")
        project = project.add_source(self._make_config(SourceType.SLACK))
        project = project.add_source(self._make_config(SourceType.BACKLOG))

        assert len(project.sources) == 2


class TestProjectRemoveSource:
    def test_remove_source_returns_project_without_source(self):
        project = Project.create(name="P")
        config = SourceConfig(
            source_type=SourceType.SLACK, sync_interval_minutes=10, is_enabled=True
        )
        project = project.add_source(config)

        updated = project.remove_source(SourceType.SLACK)

        assert len(updated.sources) == 0

    def test_remove_nonexistent_source_is_noop(self):
        project = Project.create(name="P")

        updated = project.remove_source(SourceType.SLACK)

        assert len(updated.sources) == 0


class TestProjectActiveSources:
    def test_active_sources_returns_only_enabled(self):
        project = Project.create(name="P")
        enabled = SourceConfig(
            source_type=SourceType.SLACK, sync_interval_minutes=10, is_enabled=True
        )
        disabled = SourceConfig(
            source_type=SourceType.BACKLOG, sync_interval_minutes=15, is_enabled=False
        )
        project = project.add_source(enabled)
        project = project.add_source(disabled)

        active = project.active_sources()

        assert len(active) == 1
        assert active[0].source_type == SourceType.SLACK
