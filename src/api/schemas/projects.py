"""Request/response schemas for project and context endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectContextResponse(BaseModel):
    project_id: str
    name: str
    summary: str
    active_sources: list[str]
    last_synced_at: dict[str, Optional[str]]
    document_count: int
    issue_count: int


class MemberResponse(BaseModel):
    external_id: str
    name: str
    sources: list[str]
    assigned_issue_count: int
    last_activity_at: Optional[str] = None


class MembersResponse(BaseModel):
    members: list[MemberResponse]


class MeetingSnippetResponse(BaseModel):
    id: str
    title: str
    meeting_at: str
    participants: list[str]
    summary_snippet: str


class MeetingsResponse(BaseModel):
    meetings: list[MeetingSnippetResponse]
    total: int
    limit: int
    offset: int


class ExtractedTask(BaseModel):
    title: str
    suggested_assignee: Optional[str] = None
    suggested_due_date: Optional[str] = None


class MeetingDetailResponse(BaseModel):
    id: str
    title: str
    meeting_at: str
    participants: list[str]
    raw_transcript: str
    summary: str
    decisions: list[str]
    extracted_tasks: list[ExtractedTask]
