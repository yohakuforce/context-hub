"""Project / source-config write API (admin GUI).

Fills the gap where projects and their source configs could previously only be
created by direct repository calls. All endpoints require the WRITE scope.

  GET    /api/v1/projects/detailed                       — projects + full sources
  POST   /api/v1/projects                                — create a project
  PUT    /api/v1/projects/{projectId}                    — rename / set external id
  DELETE /api/v1/projects/{projectId}                    — delete a project
  PUT    /api/v1/projects/{projectId}/sources/{type}     — create/replace a source
  DELETE /api/v1/projects/{projectId}/sources/{type}     — remove a source

Changes to source configs take effect immediately for `ingest all` and the REST
ingest path; the serve-resident background scheduler picks them up on next start.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from context_hub.api.dependencies import get_project_repo
from context_hub.api.middleware.auth import require_scope
from context_hub.api.schemas.common import ApiResponse
from context_hub.api.schemas.projects_admin import (
    CreateProjectRequest,
    ProjectDetail,
    SourceConfigView,
    UpdateProjectRequest,
    UpsertSourceRequest,
)
from context_hub.domain.project.entities import Project, SourceConfig
from context_hub.domain.project.repository import ProjectRepository
from context_hub.shared.types import ProjectId, Scope, SourceType

router = APIRouter(prefix="/projects", tags=["projects-admin"])

# Source types that have an ingestion adapter (the only ones worth configuring).
_VALID_SOURCE_TYPES = {
    SourceType.SLACK,
    SourceType.BACKLOG,
    SourceType.REDMINE,
    SourceType.EMAIL,
}


def _to_view(project: Project) -> ProjectDetail:
    return ProjectDetail(
        id=str(project.id),
        name=project.name,
        external_project_id=project.external_project_id,
        sources=[
            SourceConfigView(
                source_type=s.source_type.value,
                is_enabled=s.is_enabled,
                sync_interval_minutes=s.sync_interval_minutes,
                channel_ids=list(s.channel_ids),
                backlog_project_key=s.backlog_project_key,
                redmine_project_identifier=s.redmine_project_identifier,
            )
            for s in project.sources
        ],
    )


def _parse_source_type(source_type: str) -> SourceType:
    try:
        st = SourceType(source_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown source type: {source_type}")
    if st not in _VALID_SOURCE_TYPES:
        valid = ", ".join(sorted(t.value for t in _VALID_SOURCE_TYPES))
        raise HTTPException(
            status_code=422,
            detail=f"Source type '{source_type}' is not configurable. Use one of: {valid}",
        )
    return st


async def _load(repo: ProjectRepository, project_id: str) -> Project:
    project = await repo.find_by_id(ProjectId(project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/detailed", response_model=ApiResponse[list[ProjectDetail]])
async def list_projects_detailed(
    _consumer=Depends(require_scope(Scope.READ)),
    repo: ProjectRepository = Depends(get_project_repo),
) -> ApiResponse[list[ProjectDetail]]:
    """List all projects with their full source configurations."""
    projects = await repo.find_all()
    return ApiResponse.ok([_to_view(p) for p in projects])


@router.post("", response_model=ApiResponse[ProjectDetail])
async def create_project(
    request: CreateProjectRequest,
    _consumer=Depends(require_scope(Scope.WRITE)),
    repo: ProjectRepository = Depends(get_project_repo),
) -> ApiResponse[ProjectDetail]:
    """Create a new (empty) project."""
    project = Project.create(
        name=request.name, external_project_id=request.external_project_id
    )
    saved = await repo.save(project)
    return ApiResponse.ok(_to_view(saved))


@router.put("/{project_id}", response_model=ApiResponse[ProjectDetail])
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    _consumer=Depends(require_scope(Scope.WRITE)),
    repo: ProjectRepository = Depends(get_project_repo),
) -> ApiResponse[ProjectDetail]:
    """Rename a project and/or set its external project id."""
    project = await _load(repo, project_id)
    updated = Project(
        id=project.id,
        name=request.name if request.name is not None else project.name,
        external_project_id=(
            request.external_project_id
            if request.external_project_id is not None
            else project.external_project_id
        ),
        sources=project.sources,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
    saved = await repo.save(updated)
    return ApiResponse.ok(_to_view(saved))


@router.delete("/{project_id}", response_model=ApiResponse[dict])
async def delete_project(
    project_id: str,
    _consumer=Depends(require_scope(Scope.WRITE)),
    repo: ProjectRepository = Depends(get_project_repo),
) -> ApiResponse[dict]:
    """Delete a project."""
    await _load(repo, project_id)  # 404 if missing
    await repo.delete(ProjectId(project_id))
    return ApiResponse.ok({"deleted": project_id})


@router.put("/{project_id}/sources/{source_type}", response_model=ApiResponse[ProjectDetail])
async def upsert_source(
    project_id: str,
    source_type: str,
    request: UpsertSourceRequest,
    _consumer=Depends(require_scope(Scope.WRITE)),
    repo: ProjectRepository = Depends(get_project_repo),
) -> ApiResponse[ProjectDetail]:
    """Create or replace the configuration for one source on a project."""
    st = _parse_source_type(source_type)
    project = await _load(repo, project_id)

    config = SourceConfig(
        source_type=st,
        sync_interval_minutes=request.sync_interval_minutes,
        is_enabled=request.is_enabled,
        channel_ids=tuple(request.channel_ids),
        backlog_project_key=request.backlog_project_key,
        redmine_project_identifier=request.redmine_project_identifier,
    )
    # Replace any existing config of the same type (add_source rejects duplicates).
    project = project.remove_source(st).add_source(config)
    saved = await repo.save(project)
    return ApiResponse.ok(_to_view(saved))


@router.delete(
    "/{project_id}/sources/{source_type}", response_model=ApiResponse[ProjectDetail]
)
async def delete_source(
    project_id: str,
    source_type: str,
    _consumer=Depends(require_scope(Scope.WRITE)),
    repo: ProjectRepository = Depends(get_project_repo),
) -> ApiResponse[ProjectDetail]:
    """Remove a source configuration from a project."""
    st = _parse_source_type(source_type)
    project = await _load(repo, project_id)
    saved = await repo.save(project.remove_source(st))
    return ApiResponse.ok(_to_view(saved))
