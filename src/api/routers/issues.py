"""Issue endpoints.

GET /api/v1/projects/{projectId}/issues
GET /api/v1/projects/{projectId}/issues/{issueId}
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.middleware.auth import require_scope
from src.api.schemas.common import ApiResponse
from src.api.schemas.issues import IssueDetailSchema, IssuesResponse
from src.shared.types import Scope

router = APIRouter(prefix="/projects", tags=["issues"])


@router.get("/{project_id}/issues", response_model=ApiResponse[IssuesResponse])
async def list_issues(
    project_id: str,
    source: str = Query(..., description="backlog or redmine"),
    status: Optional[str] = Query(default="open"),
    assignee_id: Optional[str] = None,
    updated_since: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _consumer=Depends(require_scope(Scope.READ)),
) -> ApiResponse[IssuesResponse]:
    """Return paginated list of issues from Backlog or Redmine."""
    # TODO: wire to IssueRepository
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.get(
    "/{project_id}/issues/{issue_id}",
    response_model=ApiResponse[IssueDetailSchema],
)
async def get_issue(
    project_id: str,
    issue_id: str,
    include_comments: bool = True,
    _consumer=Depends(require_scope(Scope.READ)),
) -> ApiResponse[IssueDetailSchema]:
    """Return detail of a single issue including comments."""
    # TODO: wire to IssueRepository
    raise HTTPException(status_code=501, detail="Not yet implemented")
