"""Request/response schemas for ingestion/sync endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SlackSyncRequest(BaseModel):
    project_id: str
    channel_ids: list[str]
    full_resync: bool = False


class BacklogSyncRequest(BaseModel):
    project_id: str
    backlog_project_key: str
    include_wiki: bool = True
    full_resync: bool = False


class RedmineSyncRequest(BaseModel):
    project_id: str
    redmine_project_identifier: str
    include_wiki: bool = True
    full_resync: bool = False


class GmailSyncRequest(BaseModel):
    project_id: str
    # Optional Gmail search query override. When None, falls back to settings.gmail_query.
    query: Optional[str] = None
    full_resync: bool = False


class JobAcceptedResponse(BaseModel):
    job_id: str
    status: str
    estimated_duration_seconds: int


class JobStatusResponse(BaseModel):
    job_id: str
    project_id: str
    source_type: str
    status: str
    items_processed: int
    errors: list[dict]
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
