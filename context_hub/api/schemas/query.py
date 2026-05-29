"""Request/response schemas for the free-form query endpoint."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import CamelModel


class QueryFilters(CamelModel):
    updated_since: Optional[str] = None


class QueryRequest(CamelModel):
    project_id: str
    query: str = Field(..., max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    source_types: Optional[list[str]] = None
    filters: Optional[QueryFilters] = None


class QueryResultItem(CamelModel):
    document_id: str
    source_type: str
    title: str
    snippet: str
    score: float
    relevance_reason: str


class QueryResponse(CamelModel):
    results: list[QueryResultItem]
    query_embedding_model: str
