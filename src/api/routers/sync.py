"""Ingestion/sync endpoints.

POST /api/v1/sources/slack/sync
POST /api/v1/sources/backlog/sync
POST /api/v1/sources/redmine/sync
GET  /api/v1/sources/jobs/{jobId}
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from src.api.dependencies import (
    get_backlog_ingestion_service,
    get_document_repo,
    get_embedding,
    get_job_repo,
    get_issue_repo,
    get_redmine_ingestion_service,
    get_slack_ingestion_service,
)
from src.api.middleware.auth import require_scope
from src.api.schemas.common import ApiResponse
from src.api.schemas.sync import (
    BacklogSyncRequest,
    JobAcceptedResponse,
    JobStatusResponse,
    RedmineSyncRequest,
    SlackSyncRequest,
)
from src.application.ingestion_service import IngestionService
from src.domain.ingestion.entities import IngestionJob
from src.domain.ingestion.repository import IngestionJobRepository
from src.shared.types import IngestionJobId, ProjectId, Scope

router = APIRouter(prefix="/sources", tags=["sync"])


# ---------------------------------------------------------------------------
# Background task runner
# ---------------------------------------------------------------------------

async def _run_ingestion_background(
    service: IngestionService,
    project_id: ProjectId,
    full_resync: bool,
) -> None:
    """Fire-and-forget wrapper — errors are logged by IngestionService."""
    await service.run(project_id=project_id, full_resync=full_resync)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/slack/sync",
    response_model=ApiResponse[JobAcceptedResponse],
    status_code=202,
)
async def trigger_slack_sync(
    request: SlackSyncRequest,
    background_tasks: BackgroundTasks,
    _consumer=Depends(require_scope(Scope.WRITE)),
    job_repo: IngestionJobRepository = Depends(get_job_repo),
    document_repo=Depends(get_document_repo),
    issue_repo=Depends(get_issue_repo),
    embedding=Depends(get_embedding),
) -> ApiResponse[JobAcceptedResponse]:
    """Start an incremental Slack channel sync job (async, returns immediately)."""
    service = get_slack_ingestion_service(
        channel_ids=request.channel_ids,
        job_repo=job_repo,
        document_repo=document_repo,
        issue_repo=issue_repo,
        embedding=embedding,
    )
    background_tasks.add_task(
        _run_ingestion_background,
        service,
        ProjectId(request.project_id),
        request.full_resync,
    )
    return ApiResponse.ok(
        JobAcceptedResponse(
            job_id="pending",
            status="accepted",
            estimated_duration_seconds=60,
        )
    )


@router.post(
    "/backlog/sync",
    response_model=ApiResponse[JobAcceptedResponse],
    status_code=202,
)
async def trigger_backlog_sync(
    request: BacklogSyncRequest,
    background_tasks: BackgroundTasks,
    _consumer=Depends(require_scope(Scope.WRITE)),
    job_repo: IngestionJobRepository = Depends(get_job_repo),
    document_repo=Depends(get_document_repo),
    issue_repo=Depends(get_issue_repo),
    embedding=Depends(get_embedding),
) -> ApiResponse[JobAcceptedResponse]:
    """Start an incremental Backlog project sync job."""
    service = get_backlog_ingestion_service(
        backlog_project_key=request.backlog_project_key,
        include_wiki=request.include_wiki,
        job_repo=job_repo,
        document_repo=document_repo,
        issue_repo=issue_repo,
        embedding=embedding,
    )
    background_tasks.add_task(
        _run_ingestion_background,
        service,
        ProjectId(request.project_id),
        request.full_resync,
    )
    return ApiResponse.ok(
        JobAcceptedResponse(
            job_id="pending",
            status="accepted",
            estimated_duration_seconds=120,
        )
    )


@router.post(
    "/redmine/sync",
    response_model=ApiResponse[JobAcceptedResponse],
    status_code=202,
)
async def trigger_redmine_sync(
    request: RedmineSyncRequest,
    background_tasks: BackgroundTasks,
    _consumer=Depends(require_scope(Scope.WRITE)),
    job_repo: IngestionJobRepository = Depends(get_job_repo),
    document_repo=Depends(get_document_repo),
    issue_repo=Depends(get_issue_repo),
    embedding=Depends(get_embedding),
) -> ApiResponse[JobAcceptedResponse]:
    """Start an incremental Redmine project sync job."""
    service = get_redmine_ingestion_service(
        redmine_project_identifier=request.redmine_project_identifier,
        include_wiki=request.include_wiki,
        job_repo=job_repo,
        document_repo=document_repo,
        issue_repo=issue_repo,
        embedding=embedding,
    )
    background_tasks.add_task(
        _run_ingestion_background,
        service,
        ProjectId(request.project_id),
        request.full_resync,
    )
    return ApiResponse.ok(
        JobAcceptedResponse(
            job_id="pending",
            status="accepted",
            estimated_duration_seconds=120,
        )
    )


@router.get(
    "/jobs/{job_id}",
    response_model=ApiResponse[JobStatusResponse],
)
async def get_job_status(
    job_id: str,
    _consumer=Depends(require_scope(Scope.READ)),
    job_repo: IngestionJobRepository = Depends(get_job_repo),
) -> ApiResponse[JobStatusResponse]:
    """Return the current status of a sync job."""
    job: IngestionJob | None = await job_repo.find_by_id(IngestionJobId(job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return ApiResponse.ok(
        JobStatusResponse(
            job_id=str(job.id),
            project_id=str(job.project_id),
            source_type=job.source_type.value,
            status=job.status.value,
            items_processed=job.items_processed,
            errors=[
                {
                    "item_id": e.item_id,
                    "message": e.message,
                    "occurred_at": e.occurred_at.isoformat(),
                }
                for e in job.errors
            ],
            started_at=job.started_at.isoformat() if job.started_at else None,
            finished_at=job.finished_at.isoformat() if job.finished_at else None,
        )
    )
