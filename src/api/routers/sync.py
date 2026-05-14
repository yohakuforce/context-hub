"""Ingestion/sync endpoints.

POST /api/v1/sources/slack/sync
POST /api/v1/sources/backlog/sync
POST /api/v1/sources/redmine/sync
GET  /api/v1/sources/jobs/{jobId}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.middleware.auth import require_scope
from src.api.schemas.common import ApiResponse
from src.api.schemas.sync import (
    BacklogSyncRequest,
    JobAcceptedResponse,
    JobStatusResponse,
    RedmineSyncRequest,
    SlackSyncRequest,
)
from src.shared.types import Scope

router = APIRouter(prefix="/sources", tags=["sync"])


@router.post("/slack/sync", response_model=ApiResponse[JobAcceptedResponse], status_code=202)
async def trigger_slack_sync(
    request: SlackSyncRequest,
    _consumer=Depends(require_scope(Scope.WRITE)),
) -> ApiResponse[JobAcceptedResponse]:
    """Start an incremental Slack channel sync job."""
    # TODO: create IngestionJob, enqueue async task
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.post("/backlog/sync", response_model=ApiResponse[JobAcceptedResponse], status_code=202)
async def trigger_backlog_sync(
    request: BacklogSyncRequest,
    _consumer=Depends(require_scope(Scope.WRITE)),
) -> ApiResponse[JobAcceptedResponse]:
    """Start an incremental Backlog project sync job."""
    # TODO: create IngestionJob, enqueue async task
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.post("/redmine/sync", response_model=ApiResponse[JobAcceptedResponse], status_code=202)
async def trigger_redmine_sync(
    request: RedmineSyncRequest,
    _consumer=Depends(require_scope(Scope.WRITE)),
) -> ApiResponse[JobAcceptedResponse]:
    """Start an incremental Redmine project sync job."""
    # TODO: create IngestionJob, enqueue async task
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.get("/jobs/{job_id}", response_model=ApiResponse[JobStatusResponse])
async def get_job_status(
    job_id: str,
    _consumer=Depends(require_scope(Scope.READ)),
) -> ApiResponse[JobStatusResponse]:
    """Return the current status of a sync job."""
    # TODO: wire to IngestionJobRepository
    raise HTTPException(status_code=501, detail="Not yet implemented")
