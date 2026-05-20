"""Context-Hub FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from context_hub.api.middleware.error_handlers import register_error_handlers
from context_hub.api.routers import documents, issues, projects, query, sync
from context_hub.config import settings
from context_hub.mcp import MCP_PROTOCOL_VERSION

logger = structlog.get_logger()


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

    logger.info(
        "context_hub_startup",
        env=settings.app_env,
        llm_provider=settings.llm_provider,
        scheduler_backend=type(store).__name__,
        inbox_watcher_enabled=inbox_enabled,
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
            "server_version": "0.2.0",
        }

    return app


app = create_app()
