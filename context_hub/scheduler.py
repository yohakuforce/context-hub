"""APScheduler — periodic ingestion jobs.

Runs in-process with FastAPI using the AsyncIOScheduler.
Each SourceConfig with is_enabled=True and sync_interval_minutes > 0
gets a separate IntervalTrigger job.

Lifecycle:
  startup  → scheduler.start()
  shutdown → scheduler.shutdown()

The scheduler is attached to the FastAPI app in main.py via lifespan events.

Note: in INGEST_MODE=mock the adapters use fixture data, so the scheduler
can run in development without any real API keys.
"""

from __future__ import annotations

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from context_hub.config import settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return the singleton AsyncIOScheduler (created on first call)."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def schedule_project_jobs(project_id: str) -> None:
    """Register periodic sync jobs for all enabled sources of a project.

    Called from the FastAPI startup event after DB is available.
    """
    from context_hub.infrastructure.db.session import async_session as AsyncSessionFactory
    from context_hub.infrastructure.db.project_repository import PostgresProjectRepository
    from context_hub.infrastructure.db.document_repository import PostgresDocumentRepository
    from context_hub.infrastructure.db.issue_repository import PostgresIssueRepository
    from context_hub.infrastructure.db.ingestion_job_repository import (
        PostgresIngestionJobRepository,
    )
    from context_hub.infrastructure.embedding.factory import get_embedding_provider
    from context_hub.application.ingestion_service import IngestionService
    from context_hub.shared.types import ProjectId, SourceType

    ingest_mode = os.environ.get("INGEST_MODE", "mock")
    embedding = get_embedding_provider(settings.embedding_provider)
    scheduler = get_scheduler()

    async with AsyncSessionFactory() as session:
        project_repo = PostgresProjectRepository(session)
        project = await project_repo.find_by_id(ProjectId(project_id))
        if project is None:
            logger.warning("schedule_project_jobs: project %s not found", project_id)
            return

        for source in project.sources:
            if not source.is_enabled:
                continue

            job_id = f"sync_{project_id}_{source.source_type.value}"
            interval_minutes = max(source.sync_interval_minutes, 5)  # min 5 min

            trigger = IntervalTrigger(minutes=interval_minutes)

            async def _run_job(
                _project_id: str = project_id,
                _source=source,
                _ingest_mode: str = ingest_mode,
                _embedding=embedding,
            ) -> None:
                async with AsyncSessionFactory() as _session:
                    _job_repo = PostgresIngestionJobRepository(_session)
                    _doc_repo = PostgresDocumentRepository(_session)
                    _issue_repo = PostgresIssueRepository(_session)
                    adapter = _build_adapter(_source, _ingest_mode)
                    if adapter is None:
                        return
                    svc = IngestionService(
                        adapter=adapter,
                        embedding_provider=_embedding,
                        job_repo=_job_repo,
                        document_repo=_doc_repo,
                        issue_repo=_issue_repo,
                    )
                    job = await svc.run(ProjectId(_project_id))
                    logger.info(
                        "scheduled_sync_complete",
                        project_id=_project_id,
                        source=_source.source_type.value,
                        status=job.status.value,
                        items=job.items_processed,
                    )

            scheduler.add_job(
                _run_job,
                trigger=trigger,
                id=job_id,
                replace_existing=True,
                misfire_grace_time=60,
            )
            logger.info(
                "scheduled_sync_job",
                job_id=job_id,
                interval_minutes=interval_minutes,
            )


def _build_adapter(source, ingest_mode: str):
    """Build the correct SourceAdapter from a SourceConfig."""
    from context_hub.shared.types import SourceType

    match source.source_type:
        case SourceType.SLACK:
            from context_hub.infrastructure.adapters.slack.adapter import SlackAdapter
            return SlackAdapter(
                bot_token=settings.slack_bot_token or "dummy-token",
                channel_ids=list(source.channel_ids),
                ingest_mode=ingest_mode,
            )
        case SourceType.BACKLOG:
            from context_hub.infrastructure.adapters.backlog.adapter import BacklogAdapter
            return BacklogAdapter(
                space_key=settings.backlog_space_key or "dummy-space",
                api_key=settings.backlog_api_key or "dummy-key",
                backlog_project_key=source.backlog_project_key or "PROJ",
                ingest_mode=ingest_mode,
            )
        case SourceType.REDMINE:
            from context_hub.infrastructure.adapters.redmine.adapter import RedmineAdapter
            return RedmineAdapter(
                base_url=settings.redmine_base_url or "http://localhost:3000",
                api_key=settings.redmine_api_key or "dummy-key",
                redmine_project_identifier=source.redmine_project_identifier or "proj",
                ingest_mode=ingest_mode,
            )
        case SourceType.EMAIL:
            from context_hub.infrastructure.adapters.gmail.adapter import GmailAdapter
            return GmailAdapter(
                credentials_file=settings.gmail_credentials_file,
                token_file=settings.gmail_token_file,
                query=settings.gmail_query,
                ingest_mode=ingest_mode,
            )
        case _:
            logger.warning("No adapter for source type: %s", source.source_type)
            return None
