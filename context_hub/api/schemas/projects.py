"""Request/response schemas for project and context endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .common import CamelModel


class ProjectContextResponse(CamelModel):
    project_id: str
    name: str
    summary: str
    active_sources: list[str]
    last_synced_at: dict[str, Optional[str]]
    document_count: int
    issue_count: int


class MemberResponse(CamelModel):
    external_id: str
    name: str
    sources: list[str]
    assigned_issue_count: int
    last_activity_at: Optional[str] = None


class MembersResponse(CamelModel):
    members: list[MemberResponse]


class MeetingSnippetResponse(CamelModel):
    id: str
    title: str
    meeting_at: str
    participants: list[str]
    summary_snippet: str


class MeetingsResponse(CamelModel):
    meetings: list[MeetingSnippetResponse]
    total: int
    limit: int
    offset: int


class ExtractedTask(CamelModel):
    title: str
    suggested_assignee: Optional[str] = None
    suggested_due_date: Optional[str] = None


class MeetingDetailResponse(CamelModel):
    id: str
    title: str
    meeting_at: str
    participants: list[str]
    raw_transcript: str
    summary: str
    decisions: list[str]
    extracted_tasks: list[ExtractedTask]
