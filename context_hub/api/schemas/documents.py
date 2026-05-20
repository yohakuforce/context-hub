"""Request/response schemas for user-supplied document ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Source types accepted via the manual-ingest API.
# Slack/Backlog/Redmine go through their dedicated /sources/*/sync endpoints —
# accepting them here would let the API bypass adapter-specific deduplication.
UserSourceType = Literal["meeting", "file", "email"]


class DocumentCreateRequest(BaseModel):
    """Manually ingest a single text document (meeting notes, memo, email body, etc.)."""

    project_id: str = Field(..., description="Target project UUID.")
    source_type: UserSourceType = Field(
        ...,
        description="One of: meeting | file | email.",
    )
    text: str = Field(
        ...,
        min_length=1,
        description="Raw text content. May be Markdown.",
    )
    title: str | None = Field(
        None,
        description="Optional title — prepended to text as a Markdown H1 when stored.",
    )
    external_id: str | None = Field(
        None,
        description=(
            "Stable identifier for upsert deduplication. "
            "When omitted, the server generates a UUID — each call then creates a new document."
        ),
    )
    source_url: str | None = Field(
        None,
        description="Optional URL pointing back to the original source (Google Doc, Drive file, etc.).",
    )
    author: str | None = Field(
        None,
        description="Optional author identifier (email, name, slack id, ...).",
    )
    created_at: datetime | None = Field(
        None,
        description="Original creation timestamp. Defaults to server time when absent.",
    )


class DocumentResponse(BaseModel):
    document_id: str
    project_id: str
    source_type: str
    external_id: str
    embedded: bool
    created_at: str
    updated_at: str
