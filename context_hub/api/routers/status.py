"""Admin status endpoint — read-only system + projects health snapshot.

GET /api/v1/status (READ scope). Surfaces the things the GUI's Status tab shows:
active profile, ingest mode, scheduler backend, whether serve auto-sync is on,
whether vector search is degraded (FTS-only), the inbox folder, and a per-project
summary of enabled sources.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from context_hub.adapters.sqlite.session import vec_extension_available
from context_hub.api.dependencies import get_project_repo
from context_hub.api.middleware.auth import require_scope
from context_hub.api.schemas.common import ApiResponse
from context_hub.api.schemas.status import ProjectSummary, StatusResponse
from context_hub.config import settings
from context_hub.domain.project.repository import ProjectRepository
from context_hub.shared.types import Scope

router = APIRouter(tags=["status"])


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


@router.get("/status", response_model=ApiResponse[StatusResponse])
async def get_status(
    _consumer=Depends(require_scope(Scope.READ)),
    repo: ProjectRepository = Depends(get_project_repo),
) -> ApiResponse[StatusResponse]:
    """Return a read-only system + projects health snapshot."""
    projects = await repo.find_all()
    summaries = [
        ProjectSummary(
            id=str(p.id),
            name=p.name,
            enabled_sources=[s.source_type.value for s in p.active_sources()],
        )
        for p in projects
    ]

    vec_ok = vec_extension_available()
    return ApiResponse.ok(
        StatusResponse(
            profile=os.environ.get("CH_PROFILE", "quickstart"),
            ingest_mode=os.environ.get("INGEST_MODE", "mock"),
            scheduler_backend=os.environ.get("SCHEDULER_BACKEND", "memory"),
            source_sync_enabled=_truthy(os.environ.get("CH_SOURCE_SYNC_ENABLED", "true")),
            fts_degraded=not vec_ok,
            vector_search_available=vec_ok,
            inbox_dir=settings.ch_inbox_dir,
            project_count=len(projects),
            projects=summaries,
        )
    )
