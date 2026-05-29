"""FastAPI dependency providers.

All service/repository objects are constructed here and injected via Depends().
This keeps routers thin and testable — tests can override these dependencies
with mock implementations.
"""

from __future__ import annotations

import os
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
from context_hub.adapters.sqlite.ingestion_job_repository import (
    SqliteIngestionJobRepository,
)
from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
from context_hub.application.ingestion_service import IngestionService
from context_hub.application.query_service import QueryService
from context_hub.config import settings
from context_hub.config.profiles import get_profile_settings
from context_hub.domain.document.repository import DocumentRepository
from context_hub.domain.ingestion.repository import IngestionJobRepository
from context_hub.domain.issue.repository import IssueRepository
from context_hub.domain.project.repository import ProjectRepository
from context_hub.infrastructure.db.document_repository import PostgresDocumentRepository
from context_hub.infrastructure.db.ingestion_job_repository import (
    PostgresIngestionJobRepository,
)
from context_hub.infrastructure.db.issue_repository import PostgresIssueRepository
from context_hub.infrastructure.db.project_repository import PostgresProjectRepository
from context_hub.infrastructure.db.session import get_db as get_db_session
from context_hub.infrastructure.embedding.base import EmbeddingProvider
from context_hub.infrastructure.embedding.factory import get_embedding_provider

# ---------------------------------------------------------------------------
# Embedding (singleton — model loading is expensive)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_embedding_singleton() -> EmbeddingProvider:
    return get_embedding_provider(settings.embedding_provider)


def get_embedding() -> EmbeddingProvider:
    return _get_embedding_singleton()


# ---------------------------------------------------------------------------
# Repository factories
#
# Profile-aware wiring: SQLite profiles (quickstart / personal) use the plain
# sqlite3 adapters whose schema matches `context-hub migrate` and the MCP read
# path. The Postgres profile uses the SQLAlchemy ORM repos bound to a per-request
# AsyncSession. Without this split, the Postgres ORM model issues SELECTs for
# columns (embedding, content_tsv, ...) that the SQLite migrate schema lacks,
# producing a 500 on every REST read against a SQLite DB.
# ---------------------------------------------------------------------------


def _use_sqlite() -> bool:
    return get_profile_settings().database_url.startswith("sqlite")


def _sqlite_db_path() -> str:
    return get_profile_settings().ch_sqlite_db


async def get_project_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ProjectRepository:
    if _use_sqlite():
        return SqliteProjectRepository(_sqlite_db_path())
    return PostgresProjectRepository(session)


async def get_document_repo(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRepository:
    if _use_sqlite():
        return SqliteDocumentRepository(_sqlite_db_path())
    return PostgresDocumentRepository(session)


async def get_issue_repo(
    session: AsyncSession = Depends(get_db_session),
) -> IssueRepository:
    if _use_sqlite():
        return SqliteIssueRepository(_sqlite_db_path())
    return PostgresIssueRepository(session)


async def get_job_repo(
    session: AsyncSession = Depends(get_db_session),
) -> IngestionJobRepository:
    if _use_sqlite():
        return SqliteIngestionJobRepository(_sqlite_db_path())
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
