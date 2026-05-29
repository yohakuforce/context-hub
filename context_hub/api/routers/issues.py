"""Issue endpoints.

GET /api/v1/projects/{projectId}/issues
GET /api/v1/projects/{projectId}/issues/{issueId}
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from context_hub.api.dependencies import get_issue_repo
from context_hub.api.middleware.auth import require_scope
from context_hub.api.schemas.common import ApiResponse
from context_hub.api.schemas.issues import (
    AssigneeSchema,
    CommentSchema,
    IssueDetailSchema,
    IssueSchema,
    IssuesResponse,
)
from context_hub.domain.issue.entities import Issue
from context_hub.domain.issue.repository import IssueRepository
from context_hub.shared.types import IssueId, IssueStatus, ProjectId, Scope, SourceType

router = APIRouter(prefix="/projects", tags=["issues"])


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _issue_to_schema(issue: Issue) -> IssueSchema:
    """Map a domain Issue entity to IssueSchema (wire format)."""
    assignee = None
    if issue.assignee:
        assignee = AssigneeSchema(
            external_id=issue.assignee.external_id,
            name=issue.assignee.name,
        )
    return IssueSchema(
        id=str(issue.id),
        source_type=issue.source_type.value,
        external_id=issue.external_id,
        title=issue.title,
        description=issue.description,
        status=issue.status.value,
        priority=issue.priority.value,
        assignee=assignee,
        due_date=issue.due_date.isoformat() if issue.due_date else None,
        labels=list(issue.labels),
        comment_count=len(issue.comments),
        created_at=issue.created_at.isoformat(),
        updated_at=issue.updated_at.isoformat(),
    )


def _issue_to_detail_schema(issue: Issue) -> IssueDetailSchema:
    """Map a domain Issue entity to IssueDetailSchema (includes comments)."""
    base = _issue_to_schema(issue)
    comments = [
        CommentSchema(
            id=str(c.id),
            author=AssigneeSchema(
                external_id=c.author.external_id,
                name=c.author.name,
            ),
            body=c.body,
            created_at=c.created_at.isoformat(),
        )
        for c in issue.comments
    ]
    return IssueDetailSchema(
        id=base.id,
        source_type=base.source_type,
        external_id=base.external_id,
        title=base.title,
        description=base.description,
        status=base.status,
        priority=base.priority,
        assignee=base.assignee,
        due_date=base.due_date,
        labels=base.labels,
        comment_count=base.comment_count,
        created_at=base.created_at,
        updated_at=base.updated_at,
        comments=comments,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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
    issue_repo: IssueRepository = Depends(get_issue_repo),
) -> ApiResponse[IssuesResponse]:
    """Return paginated list of issues from Backlog or Redmine."""
    pid = ProjectId(project_id)

    source_type: Optional[SourceType] = None
    if source:
        try:
            source_type = SourceType(source)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown source: {source!r}")

    issue_status: Optional[IssueStatus] = None
    if status:
        try:
            issue_status = IssueStatus(status)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown status: {status!r}")

    if updated_since:
        try:
            since_dt = datetime.fromisoformat(updated_since)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid updated_since format; use ISO-8601")
        if source_type is None:
            raise HTTPException(status_code=422, detail="source is required when updated_since is provided")
        issues = await issue_repo.find_updated_since(pid, source_type, since_dt)
        total = len(issues)
        issues = issues[offset: offset + limit]
    else:
        issues = await issue_repo.find_by_project(
            pid,
            source_type=source_type,
            status=issue_status,
            assignee_id=assignee_id,
            limit=limit,
            offset=offset,
        )
        total = await issue_repo.count_by_project(pid, source_type=source_type)

    return ApiResponse.ok(
        IssuesResponse(
            issues=[_issue_to_schema(i) for i in issues],
            total=total,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/{project_id}/issues/{issue_id}",
    response_model=ApiResponse[IssueDetailSchema],
)
async def get_issue(
    project_id: str,
    issue_id: str,
    include_comments: bool = True,
    _consumer=Depends(require_scope(Scope.READ)),
    issue_repo: IssueRepository = Depends(get_issue_repo),
) -> ApiResponse[IssueDetailSchema]:
    """Return detail of a single issue including comments."""
    issue = await issue_repo.find_by_id(IssueId(issue_id))
    if issue is None or str(issue.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Issue not found")

    detail = _issue_to_detail_schema(issue)
    if not include_comments:
        detail = IssueDetailSchema(
            id=detail.id,
            source_type=detail.source_type,
            external_id=detail.external_id,
            title=detail.title,
            description=detail.description,
            status=detail.status,
            priority=detail.priority,
            assignee=detail.assignee,
            due_date=detail.due_date,
            labels=detail.labels,
            comment_count=detail.comment_count,
            created_at=detail.created_at,
            updated_at=detail.updated_at,
            comments=[],
        )
    return ApiResponse.ok(detail)
