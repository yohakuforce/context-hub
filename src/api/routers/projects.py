"""Project context endpoints.

GET /api/v1/projects/{projectId}/context
GET /api/v1/projects/{projectId}/members
GET /api/v1/projects/{projectId}/meetings
GET /api/v1/projects/{projectId}/meetings/{meetingId}
GET /api/v1/projects/{projectId}/documents
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.middleware.auth import require_scope
from src.api.schemas.common import ApiResponse
from src.api.schemas.projects import (
    MeetingDetailResponse,
    MeetingsResponse,
    MembersResponse,
    ProjectContextResponse,
)
from src.shared.types import Scope

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}/context", response_model=ApiResponse[ProjectContextResponse])
async def get_project_context(
    project_id: str,
    type: Literal["overview", "full"] = "overview",
    sources: Optional[list[str]] = Query(default=None),
    _consumer=Depends(require_scope(Scope.READ)),
) -> ApiResponse[ProjectContextResponse]:
    """Return a summary of the project's collected context.

    This is a stub implementation — full logic wired in Step 2.
    """
    # TODO: wire to ProjectContextService
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.get("/{project_id}/members", response_model=ApiResponse[MembersResponse])
async def get_project_members(
    project_id: str,
    source: Optional[str] = None,
    _consumer=Depends(require_scope(Scope.READ)),
) -> ApiResponse[MembersResponse]:
    """Return project member information aggregated from all sources."""
    # TODO: wire to MemberService
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.get("/{project_id}/meetings", response_model=ApiResponse[MeetingsResponse])
async def list_meetings(
    project_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    _consumer=Depends(require_scope(Scope.READ)),
) -> ApiResponse[MeetingsResponse]:
    """Return paginated meeting list for the project."""
    # TODO: wire to DocumentRepository filtered by sourceType=MEETING
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.get(
    "/{project_id}/meetings/{meeting_id}",
    response_model=ApiResponse[MeetingDetailResponse],
)
async def get_meeting(
    project_id: str,
    meeting_id: str,
    _consumer=Depends(require_scope(Scope.READ)),
) -> ApiResponse[MeetingDetailResponse]:
    """Return full detail of a single meeting document."""
    # TODO: wire to DocumentRepository
    raise HTTPException(status_code=501, detail="Not yet implemented")
