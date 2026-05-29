"""Request/response schemas for issue endpoints."""

from __future__ import annotations

from typing import Optional

from .common import CamelModel


class AssigneeSchema(CamelModel):
    external_id: str
    name: str


class CommentSchema(CamelModel):
    id: str
    author: AssigneeSchema
    body: str
    created_at: str


class IssueSchema(CamelModel):
    id: str
    source_type: str
    external_id: str
    title: str
    description: str
    status: str
    priority: str
    assignee: Optional[AssigneeSchema] = None
    due_date: Optional[str] = None
    labels: list[str]
    comment_count: int
    created_at: str
    updated_at: str


class IssueDetailSchema(IssueSchema):
    comments: list[CommentSchema]


class IssuesResponse(CamelModel):
    issues: list[IssueSchema]
    total: int
    limit: int
    offset: int
