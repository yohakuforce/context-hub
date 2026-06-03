"""Context-Hub FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from context_hub.api.middleware.error_handlers import register_error_handlers
from context_hub.api.routers import (
    config,
    documents,
    ingest,
    issues,
    projects,
    projects_admin,
    query,
    status,
    sync,
)
from context_hub.config import settings
from context_hub.mcp import MCP_PROTOCOL_VERSION

logger = structlog.get_logger()


def _server_version() -> str:
    """Resolve the installed package version (single source of truth).

    Falls back to "0+unknown" when running from a source tree that was never
    installed (e.g. some CI checkouts), so the endpoint never raises.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("yohakuforce-context-hub")
    except PackageNotFoundError:
        return "0+unknown"


SERVER_VERSION = _server_version()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle.

    Startup:
        - Initialise the APScheduler with the configured jobstore backend.
        - Start the scheduler event loop integration.

    Shutdown:
        - Drain in-flight jobs (wait=True) before the process exits.
        - Notify the scheduler store so it can flush any pending I/O.

    The scheduler backend is selected by ``SCHEDULER_BACKEND`` env var:
    - ``memory``   — zero-dependency in-process store (default, quickstart)
    - ``sqlite``   — persistent SQLite with WAL mode (personal profile)
    - ``postgres`` — PostgreSQL-backed store (production profile)
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from context_hub.adapters.scheduler.factory import get_scheduler_store

    scheduler = AsyncIOScheduler(timezone="UTC")
    store = get_scheduler_store()
    store.bind(scheduler)
    scheduler.start()

    inbox_enabled = _register_inbox_job(scheduler)

    # B-2: periodically sync every enabled external source (Slack/Backlog/
    # Redmine/Gmail) for all projects while `serve` is running — full automation
    # without a separate launchd/cron job. Never let registration crash startup.
    try:
        source_sync_jobs = await _register_source_sync_jobs(scheduler)
    except Exception:  # noqa: BLE001
        source_sync_jobs = 0
        logger.warning("source_sync_registration_failed", exc_info=True)

    logger.info(
        "context_hub_startup",
        env=settings.app_env,
        llm_provider=settings.llm_provider,
        scheduler_backend=type(store).__name__,
        inbox_watcher_enabled=inbox_enabled,
        source_sync_jobs=source_sync_jobs,
    )

    yield

    # Graceful shutdown: wait for running jobs before stopping.
    # try/finally guarantees store.shutdown is called even if scheduler.shutdown raises.
    try:
        scheduler.shutdown(wait=True)
    finally:
        await store.shutdown(graceful=True)
    logger.info("context_hub_shutdown")


def _register_inbox_job(scheduler) -> bool:
    """Wire the inbox folder watcher into the scheduler when CH_INBOX_DIR is set.

    Returns True when a job was registered, False when disabled.
    """
    from pathlib import Path

    from apscheduler.triggers.interval import IntervalTrigger

    inbox_dir_raw = settings.ch_inbox_dir
    if not inbox_dir_raw:
        return False

    inbox_dir = Path(inbox_dir_raw).expanduser()
    poll_seconds = max(int(settings.ch_inbox_poll_seconds), 5)
    project_id = settings.ch_project_id

    async def _run_inbox_scan() -> None:
        from context_hub.infrastructure.db.session import async_session as AsyncSessionFactory
        from context_hub.infrastructure.db.document_repository import PostgresDocumentRepository
        from context_hub.infrastructure.db.project_repository import PostgresProjectRepository
        from context_hub.infrastructure.embedding.factory import get_embedding_provider
        from context_hub.services.inbox_watcher import scan_inbox

        embedding = get_embedding_provider(settings.embedding_provider)
        async with AsyncSessionFactory() as session:
            project_repo = PostgresProjectRepository(session)
            document_repo = PostgresDocumentRepository(session)
            result = await scan_inbox(
                inbox_dir=inbox_dir,
                project_repo=project_repo,
                document_repo=document_repo,
                embedding=embedding,
                configured_project_id=project_id,
            )
            if result.changed_count or result.errors:
                logger.info("inbox_scan_result", **result.as_dict())

    scheduler.add_job(
        _run_inbox_scan,
        trigger=IntervalTrigger(seconds=poll_seconds),
        id="inbox_watcher",
        replace_existing=True,
        misfire_grace_time=30,
    )
    logger.info(
        "inbox_watcher_registered",
        inbox_dir=str(inbox_dir),
        poll_seconds=poll_seconds,
    )
    return True


# ---------------------------------------------------------------------------
# B-2: serve-resident periodic source sync (all enabled external sources)
# ---------------------------------------------------------------------------

# Source types that have an ingestion adapter (vs. document-only types).
_SYNCABLE_SOURCE_TYPES = ("slack", "backlog", "redmine", "email")

# Minimum interval to avoid hammering external APIs / overlapping runs.
_MIN_SYNC_INTERVAL_MINUTES = 5
_DEFAULT_SYNC_INTERVAL_MINUTES = 15


def _source_sync_enabled() -> bool:
    """Whether serve-resident periodic source sync is on (default: on)."""
    import os

    return os.environ.get("CH_SOURCE_SYNC_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def _list_projects_for_sync() -> list:
    """Return all projects via the profile-aware repository (may hit the DB)."""
    from context_hub.config.profiles import get_profile_settings

    s = get_profile_settings()
    if s.database_url.startswith("sqlite"):
        from context_hub.adapters.sqlite.project_repository import (
            SqliteProjectRepository,
        )

        return await SqliteProjectRepository(s.ch_sqlite_db).find_all()

    from context_hub.infrastructure.db.project_repository import (
        PostgresProjectRepository,
    )
    from context_hub.infrastructure.db.session import async_session

    async with async_session() as session:
        return await PostgresProjectRepository(session).find_all()


def _make_source_sync_job(
    project_id: str, source_config: object, ingest_mode: str
) -> Callable[[], Awaitable[None]]:
    """Build the coroutine that runs one source's ingestion, profile-aware.

    Failures are logged and swallowed so a single bad source never crashes the
    scheduler or affects other jobs.
    """

    async def _run() -> None:
        from context_hub.application.ingestion_service import IngestionService
        from context_hub.config.profiles import get_profile_settings
        from context_hub.infrastructure.embedding.factory import get_embedding_provider
        from context_hub.scheduler import _build_adapter
        from context_hub.shared.types import ProjectId

        source_name = getattr(source_config.source_type, "value", "unknown")  # type: ignore[attr-defined]
        try:
            adapter = _build_adapter(source_config, ingest_mode)
            if adapter is None:
                return
            s = get_profile_settings()
            embedding = get_embedding_provider(s.embedding_provider)

            if s.database_url.startswith("sqlite"):
                from context_hub.adapters.sqlite.document_repository import (
                    SqliteDocumentRepository,
                )
                from context_hub.adapters.sqlite.ingestion_job_repository import (
                    SqliteIngestionJobRepository,
                )
                from context_hub.adapters.sqlite.issue_repository import (
                    SqliteIssueRepository,
                )

                db = s.ch_sqlite_db
                service = IngestionService(
                    adapter=adapter,
                    embedding_provider=embedding,
                    job_repo=SqliteIngestionJobRepository(db),
                    document_repo=SqliteDocumentRepository(db),
                    issue_repo=SqliteIssueRepository(db),
                )
                job = await service.run(ProjectId(project_id))
            else:
                from context_hub.infrastructure.db.document_repository import (
                    PostgresDocumentRepository,
                )
                from context_hub.infrastructure.db.ingestion_job_repository import (
                    PostgresIngestionJobRepository,
                )
                from context_hub.infrastructure.db.issue_repository import (
                    PostgresIssueRepository,
                )
                from context_hub.infrastructure.db.session import async_session

                async with async_session() as session:
                    service = IngestionService(
                        adapter=adapter,
                        embedding_provider=embedding,
                        job_repo=PostgresIngestionJobRepository(session),
                        document_repo=PostgresDocumentRepository(session),
                        issue_repo=PostgresIssueRepository(session),
                    )
                    job = await service.run(ProjectId(project_id))

            logger.info(
                "scheduled_source_sync_complete",
                project_id=project_id,
                source=source_name,
                status=job.status.value,
                items=job.items_processed,
            )
        except Exception:  # noqa: BLE001 — a job failure must not kill the scheduler
            logger.warning(
                "scheduled_source_sync_failed",
                project_id=project_id,
                source=source_name,
                exc_info=True,
            )

    return _run


async def _register_source_sync_jobs(scheduler: object) -> int:
    """Register an interval sync job per enabled external source, across projects.

    Returns the number of jobs registered. Disabled via ``CH_SOURCE_SYNC_ENABLED=false``.
    """
    import os

    if not _source_sync_enabled():
        return 0

    from apscheduler.triggers.interval import IntervalTrigger

    ingest_mode = os.environ.get("INGEST_MODE", "mock")
    try:
        projects = await _list_projects_for_sync()
    except Exception:  # noqa: BLE001 — no DB / not migrated yet: register nothing
        logger.warning("source_sync_project_listing_failed", exc_info=True)
        return 0

    count = 0
    for project in projects:
        for source in project.active_sources():
            if source.source_type.value not in _SYNCABLE_SOURCE_TYPES:
                continue
            interval = max(
                int(
                    getattr(source, "sync_interval_minutes", 0)
                    or _DEFAULT_SYNC_INTERVAL_MINUTES
                ),
                _MIN_SYNC_INTERVAL_MINUTES,
            )
            job_id = f"sync_{project.id}_{source.source_type.value}"
            scheduler.add_job(  # type: ignore[attr-defined]
                _make_source_sync_job(str(project.id), source, ingest_mode),
                trigger=IntervalTrigger(minutes=interval),
                id=job_id,
                replace_existing=True,
                misfire_grace_time=60,
            )
            count += 1

    logger.info("source_sync_jobs_registered", count=count)
    return count


def create_app() -> FastAPI:
    """Factory function that creates and configures the FastAPI app."""
    app = FastAPI(
        title="Context-Hub API",
        description="Context collection and storage foundation for AI projects",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
    )

    # --- CORS (restrict in production) ---
    # allow_credentials must be False when allow_origins contains "*".
    # Per CORS spec, browsers reject "Access-Control-Allow-Credentials: true"
    # combined with a wildcard origin, so setting it True would be a no-op
    # at best and misleading at worst.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else [],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Error handlers ---
    register_error_handlers(app)

    # --- Routers ---
    api_prefix = "/api/v1"
    app.include_router(projects.router, prefix=api_prefix)
    app.include_router(issues.router, prefix=api_prefix)
    app.include_router(query.router, prefix=api_prefix)
    app.include_router(sync.router, prefix=api_prefix)
    app.include_router(documents.router, prefix=api_prefix)
    app.include_router(ingest.router, prefix=api_prefix)
    app.include_router(config.router, prefix=api_prefix)
    app.include_router(projects_admin.router, prefix=api_prefix)
    app.include_router(status.router, prefix=api_prefix)

    # --- Admin GUI (server-rendered, no build step) ---
    from fastapi.responses import HTMLResponse

    from context_hub.api.admin_ui import render_admin_page

    @app.get("/admin", tags=["admin"], response_class=HTMLResponse)
    async def admin_ui() -> str:
        """Serve the single-page admin console (settings, sources, status).

        The page shell is unauthenticated (localhost-only deployment); every data
        call it makes carries the API key the user enters, and those endpoints
        require the ADMIN scope.
        """
        return render_admin_page()

    # --- Health check (no auth required) ---
    # Intentionally returns only {"status": "ok"} to avoid environment
    # fingerprinting. Env details are available at /mcp/version (internal use).
    @app.get("/health", tags=["ops"])
    async def health() -> dict:
        return {"status": "ok"}

    # --- MCP version check (AI-PM can call this at startup to verify compatibility) ---
    @app.get("/mcp/version", tags=["mcp"])
    async def mcp_version() -> dict:
        """Return the MCP protocol version supported by this server.

        AI-PM (Claude Desktop / Claude Code) should call this at startup
        to verify transport compatibility before opening the stdio channel.
        """
        return {
            "mcp_protocol_version": MCP_PROTOCOL_VERSION,
            "server": "context-hub",
            "server_version": SERVER_VERSION,
        }

    return app


app = create_app()
