"""Schema for the admin status endpoint (GET /api/v1/status)."""

from __future__ import annotations

from .common import CamelModel


class ProjectSummary(CamelModel):
    id: str
    name: str
    enabled_sources: list[str]


class StatusResponse(CamelModel):
    """Read-only system + projects health snapshot for the admin GUI."""

    profile: str
    ingest_mode: str
    scheduler_backend: str
    source_sync_enabled: bool
    fts_degraded: bool
    vector_search_available: bool
    inbox_dir: str | None
    project_count: int
    projects: list[ProjectSummary]
