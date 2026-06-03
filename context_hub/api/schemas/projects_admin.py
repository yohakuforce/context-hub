"""Schemas for project / source-config CRUD (admin GUI write API)."""

from __future__ import annotations

from .common import CamelModel


class SourceConfigView(CamelModel):
    """A project's configuration for one data source."""

    source_type: str
    is_enabled: bool
    sync_interval_minutes: int
    channel_ids: list[str]
    backlog_project_key: str | None
    redmine_project_identifier: str | None


class ProjectDetail(CamelModel):
    """A project with its full source-config list (camelCase)."""

    id: str
    name: str
    external_project_id: str | None
    sources: list[SourceConfigView]


class CreateProjectRequest(CamelModel):
    name: str
    external_project_id: str | None = None


class UpdateProjectRequest(CamelModel):
    name: str | None = None
    external_project_id: str | None = None


class UpsertSourceRequest(CamelModel):
    """Create or replace a source config. ``sourceType`` comes from the URL path."""

    is_enabled: bool = True
    sync_interval_minutes: int = 15
    channel_ids: list[str] = []
    backlog_project_key: str | None = None
    redmine_project_identifier: str | None = None
