"""Ingestion endpoints for externally-scraped source data.

POST /api/v1/projects/{projectId}/ingest/slack
    Push a batch of scraped Slack messages. Each message becomes a slack
    Document keyed on its Slack ts (idempotent upsert). This is the path for
    Slack content obtained by web scraping rather than the Slack API.

Backlog / Redmine are ingested via their API adapters (keys configured),
not through this scraped-push endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from context_hub.api.dependencies import (
    get_document_repo,
    get_embedding,
    get_project_repo,
)
from context_hub.api.middleware.auth import require_scope
from context_hub.api.schemas.common import ApiResponse
from context_hub.api.schemas.ingest import SlackIngestRequest, SlackIngestResponse
from context_hub.domain.document.entities import Document
from context_hub.domain.document.repository import DocumentRepository
from context_hub.domain.project.repository import ProjectRepository
from context_hub.infrastructure.embedding.base import EmbeddingProvider
from context_hub.shared.types import ProjectId, RawContent, Scope, SourceType

router = APIRouter(prefix="/projects", tags=["ingest"])


def _ts_to_datetime(ts: str) -> datetime:
    """Slack ts is a Unix epoch float ('1716800000.001'). Fallback to now()."""
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC)
    except (ValueError, OSError):
        return datetime.now(UTC)


@router.post(
    "/{project_id}/ingest/slack",
    response_model=ApiResponse[SlackIngestResponse],
    status_code=201,
)
async def ingest_slack(
    project_id: str,
    request: SlackIngestRequest,
    _consumer=Depends(require_scope(Scope.WRITE)),
    project_repo: ProjectRepository = Depends(get_project_repo),
    document_repo: DocumentRepository = Depends(get_document_repo),
    embedding: EmbeddingProvider = Depends(get_embedding),
) -> ApiResponse[SlackIngestResponse]:
    """Upsert scraped Slack messages as slack Documents (idempotent on ts)."""
    pid = ProjectId(project_id)
    if await project_repo.find_by_id(pid) is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    ingested = 0
    updated = 0
    skipped = 0
    document_ids: list[str] = []

    for msg in request.messages:
        if not msg.ts or not (msg.text or "").strip():
            skipped += 1
            continue

        existing = await document_repo.find_by_external_id(
            pid, SourceType.SLACK, msg.ts
        )
        document = Document.create(
            project_id=pid,
            source_type=SourceType.SLACK,
            external_id=msg.ts,
            raw_content=RawContent(
                text=msg.text,
                source_url=msg.permalink,
                author_id=msg.user_name or msg.user,
                created_at=_ts_to_datetime(msg.ts),
            ),
        )
        vector = await embedding.embed(msg.text)
        document = document.with_embedding(vector)
        saved = await document_repo.save(document)

        document_ids.append(str(saved.id))
        if existing is None:
            ingested += 1
        else:
            updated += 1

    return ApiResponse.ok(
        SlackIngestResponse(
            ingested=ingested,
            updated=updated,
            skipped=skipped,
            document_ids=document_ids,
        )
    )
