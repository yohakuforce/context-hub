"""FastAPI dependency providers.

All service/repository objects are constructed here and injected via Depends().
This keeps routers thin and testable — tests can override these dependencies
with mock implementations.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from context_hub.config import settings
from context_hub.infrastructure.db.session import get_db as get_db_session
from context_hub.infrastructure.db.document_repository import PostgresDocumentRepository
from context_hub.infrastructure.db.ingestion_job_repository import (
    PostgresIngestionJobRepository,
)
from context_hub.infrastructure.db.issue_repository import PostgresIssueRepository
from context_hub.infrastructure.db.project_repository import PostgresProjectRepository
from context_hub.infrastructure.embedding.factory import get_embedding_provider
from context_hub.infrastructure.embedding.base import EmbeddingProvider
from context_hub.application.ingestion_service import IngestionService
from context_hub.application.query_service import QueryService
from context_hub.domain.document.repository import DocumentRepository
from context_hub.domain.ingestion.repository import IngestionJobRepository
from context_hub.domain.issue.repository import IssueRepository
from context_hub.domain.project.repository import ProjectRepository


# ---------------------------------------------------------------------------
# Embedding (singleton — model loading is expensive)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_embedding_singleton() -> EmbeddingProvider:
    return get_embedding_provider(settings.embedding_provider)


def get_embedding() -> EmbeddingProvider:
    return _get_embedding_singleton()


# ---------------------------------------------------------------------------
# Repository factories (scoped per request via AsyncSession)
# ---------------------------------------------------------------------------

async def get_project_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ProjectRepository:
    return PostgresProjectRepository(session)


async def get_document_repo(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRepository:
    return PostgresDocumentRepository(session)


async def get_issue_repo(
    session: AsyncSession = Depends(get_db_session),
) -> IssueRepository:
    return PostgresIssueRepository(session)


async def get_job_repo(
    session: AsyncSession = Depends(get_db_session),
) -> IngestionJobRepository:
    return PostgresIngestionJobRepository(session)


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------

async def get_query_service(
    document_repo: DocumentRepository = Depends(get_document_repo),
    embedding: EmbeddingProvider = Depends(get_embedding),
) -> QueryService:
    return QueryService(
        document_repo=document_repo,
        embedding_provider=embedding,
    )


def _make_ingestion_service(
    adapter,
    job_repo: IngestionJobRepository,
    document_repo: DocumentRepository,
    issue_repo: IssueRepository,
    embedding: EmbeddingProvider,
) -> IngestionService:
    return IngestionService(
        adapter=adapter,
        embedding_provider=embedding,
        job_repo=job_repo,
        document_repo=document_repo,
        issue_repo=issue_repo,
    )


def _ingest_mode() -> str:
    return os.environ.get("INGEST_MODE", "mock")


def get_slack_ingestion_service(
    channel_ids: list[str],
    job_repo: IngestionJobRepository,
    document_repo: DocumentRepository,
    issue_repo: IssueRepository,
    embedding: EmbeddingProvider,
) -> IngestionService:
    from context_hub.infrastructure.adapters.slack.adapter import SlackAdapter

    adapter = SlackAdapter(
        bot_token=settings.slack_bot_token or "dummy-token",
        channel_ids=channel_ids,
        ingest_mode=_ingest_mode(),
    )
    return _make_ingestion_service(adapter, job_repo, document_repo, issue_repo, embedding)


def get_backlog_ingestion_service(
    backlog_project_key: str,
    include_wiki: bool,
    job_repo: IngestionJobRepository,
    document_repo: DocumentRepository,
    issue_repo: IssueRepository,
    embedding: EmbeddingProvider,
) -> IngestionService:
    from context_hub.infrastructure.adapters.backlog.adapter import BacklogAdapter

    adapter = BacklogAdapter(
        space_key=settings.backlog_space_key or "dummy-space",
        api_key=settings.backlog_api_key or "dummy-key",
        backlog_project_key=backlog_project_key,
        include_wiki=include_wiki,
        ingest_mode=_ingest_mode(),
    )
    return _make_ingestion_service(adapter, job_repo, document_repo, issue_repo, embedding)


def get_redmine_ingestion_service(
    redmine_project_identifier: str,
    include_wiki: bool,
    job_repo: IngestionJobRepository,
    document_repo: DocumentRepository,
    issue_repo: IssueRepository,
    embedding: EmbeddingProvider,
) -> IngestionService:
    from context_hub.infrastructure.adapters.redmine.adapter import RedmineAdapter

    adapter = RedmineAdapter(
        base_url=settings.redmine_base_url or "http://localhost:3000",
        api_key=settings.redmine_api_key or "dummy-key",
        redmine_project_identifier=redmine_project_identifier,
        include_wiki=include_wiki,
        ingest_mode=_ingest_mode(),
    )
    return _make_ingestion_service(adapter, job_repo, document_repo, issue_repo, embedding)


def get_gmail_ingestion_service(
    query: str | None,
    job_repo: IngestionJobRepository,
    document_repo: DocumentRepository,
    issue_repo: IssueRepository,
    embedding: EmbeddingProvider,
) -> IngestionService:
    from context_hub.infrastructure.adapters.gmail.adapter import GmailAdapter

    adapter = GmailAdapter(
        credentials_file=settings.gmail_credentials_file,
        token_file=settings.gmail_token_file,
        query=query or settings.gmail_query,
        ingest_mode=_ingest_mode(),
    )
    return _make_ingestion_service(adapter, job_repo, document_repo, issue_repo, embedding)
