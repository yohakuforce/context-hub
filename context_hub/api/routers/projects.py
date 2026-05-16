"""Project context endpoints.

GET /api/v1/projects
GET /api/v1/projects/{projectId}/context
GET /api/v1/projects/{projectId}/members
GET /api/v1/projects/{projectId}/meetings
GET /api/v1/projects/{projectId}/meetings/{meetingId}
GET /api/v1/projects/{projectId}/documents
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from context_hub.api.dependencies import get_document_repo, get_issue_repo, get_project_repo
from context_hub.api.middleware.auth import require_scope
from context_hub.api.schemas.common import ApiResponse, PaginatedMeta
from context_hub.api.schemas.projects import (
    MeetingDetailResponse,
    MeetingsResponse,
    MeetingSnippetResponse,
    MembersResponse,
    MemberResponse,
    ProjectContextResponse,
)
from context_hub.domain.document.repository import DocumentRepository
from context_hub.domain.issue.repository import IssueRepository
from context_hub.domain.project.repository import ProjectRepository
from context_hub.shared.types import ProjectId, Scope, SourceType

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Project list
# ---------------------------------------------------------------------------

@router.get("", response_model=ApiResponse[list[dict]])
async def list_projects(
    _consumer=Depends(require_scope(Scope.READ)),
    project_repo: ProjectRepository = Depends(get_project_repo),
) -> ApiResponse[list[dict]]:
    """Return all registered projects."""
    projects = await project_repo.find_all()
    return ApiResponse.ok(
        [
            {
                "project_id": str(p.id),
                "name": p.name,
                "external_project_id": p.external_project_id,
                "source_count": len(p.sources),
            }
            for p in projects
        ]
    )


# ---------------------------------------------------------------------------
# Project context summary
# ---------------------------------------------------------------------------

@router.get("/{project_id}/context", response_model=ApiResponse[ProjectContextResponse])
async def get_project_context(
    project_id: str,
    type: Literal["overview", "full"] = "overview",
    sources: Optional[list[str]] = Query(default=None),
    _consumer=Depends(require_scope(Scope.READ)),
    project_repo: ProjectRepository = Depends(get_project_repo),
    document_repo: DocumentRepository = Depends(get_document_repo),
    issue_repo: IssueRepository = Depends(get_issue_repo),
) -> ApiResponse[ProjectContextResponse]:
    """Return a summary of the project's collected context."""
    pid = ProjectId(project_id)
    project = await project_repo.find_by_id(pid)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    doc_count = await document_repo.count_by_project(pid)
    issue_count = await issue_repo.count_by_project(pid)

    active_sources = [
        s.source_type.value for s in project.sources if s.is_enabled
    ]

    return ApiResponse.ok(
        ProjectContextResponse(
            project_id=project_id,
            name=project.name,
            summary=f"Project '{project.name}' has {doc_count} documents and {issue_count} issues.",
            active_sources=active_sources,
            last_synced_at={s: None for s in active_sources},
            document_count=doc_count,
            issue_count=issue_count,
        )
    )


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

@router.get("/{project_id}/members", response_model=ApiResponse[MembersResponse])
async def get_project_members(
    project_id: str,
    source: Optional[str] = None,
    _consumer=Depends(require_scope(Scope.READ)),
    issue_repo: IssueRepository = Depends(get_issue_repo),
) -> ApiResponse[MembersResponse]:
    """Return project member information aggregated from issues."""
    pid = ProjectId(project_id)
    source_type = SourceType(source) if source else None
    issues = await issue_repo.find_by_project(pid, source_type=source_type, limit=500)

    # Aggregate members from assignee fields
    member_map: dict[str, MemberResponse] = {}
    for issue in issues:
        if issue.assignee:
            key = issue.assignee.external_id
            if key not in member_map:
                member_map[key] = MemberResponse(
                    external_id=key,
                    name=issue.assignee.name,
                    sources=[issue.source_type.value],
                    assigned_issue_count=0,
                )
            else:
                # Immutable update via direct field access (read model only)
                existing = member_map[key]
                if issue.source_type.value not in existing.sources:
                    existing.sources.append(issue.source_type.value)
            member_map[key] = MemberResponse(
                external_id=key,
                name=member_map[key].name,
                sources=member_map[key].sources,
                assigned_issue_count=member_map[key].assigned_issue_count + 1,
            )

    return ApiResponse.ok(MembersResponse(members=list(member_map.values())))


# ---------------------------------------------------------------------------
# Meetings (Documents with source_type=MEETING)
# ---------------------------------------------------------------------------

@router.get("/{project_id}/meetings", response_model=ApiResponse[MeetingsResponse])
async def list_meetings(
    project_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    _consumer=Depends(require_scope(Scope.READ)),
    document_repo: DocumentRepository = Depends(get_document_repo),
) -> ApiResponse[MeetingsResponse]:
    """Return paginated meeting list for the project."""
    pid = ProjectId(project_id)
    meetings = await document_repo.find_by_project(
        project_id=pid,
        source_type=SourceType.MEETING,
        limit=limit,
        offset=offset,
    )
    total = await document_repo.count_by_project(pid, source_type=SourceType.MEETING)

    snippets = [
        MeetingSnippetResponse(
            id=str(m.id),
            title=_derive_title(m),
            meeting_at=m.raw_content.created_at.isoformat(),
            participants=[],
            summary_snippet=(
                m.structured_content.summary[:200]
                if m.structured_content
                else m.raw_content.text[:200]
            ),
        )
        for m in meetings
    ]

    return ApiResponse.ok(
        MeetingsResponse(
            meetings=snippets,
            total=total,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/{project_id}/meetings/{meeting_id}",
    response_model=ApiResponse[MeetingDetailResponse],
)
async def get_meeting(
    project_id: str,
    meeting_id: str,
    _consumer=Depends(require_scope(Scope.READ)),
    document_repo: DocumentRepository = Depends(get_document_repo),
) -> ApiResponse[MeetingDetailResponse]:
    """Return full detail of a single meeting document."""
    from context_hub.shared.types import DocumentId

    doc = await document_repo.find_by_id(DocumentId(meeting_id))
    if doc is None or doc.source_type != SourceType.MEETING:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return ApiResponse.ok(
        MeetingDetailResponse(
            id=str(doc.id),
            title=_derive_title(doc),
            meeting_at=doc.raw_content.created_at.isoformat(),
            participants=[],
            raw_transcript=doc.raw_content.text,
            summary=(
                doc.structured_content.summary if doc.structured_content else ""
            ),
            decisions=[],
            extracted_tasks=[],
        )
    )


def _derive_title(doc) -> str:
    if doc.structured_content and doc.structured_content.summary:
        return doc.structured_content.summary[:80]
    raw = doc.raw_content.text or ""
    first_line = raw.split("\n")[0].strip()
    return first_line[:80] if first_line else f"[{doc.source_type.value}]"
