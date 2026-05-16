"""Context-Hub FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.error_handlers import register_error_handlers
from src.api.routers import issues, projects, query, sync
from src.config import settings
from src.mcp import MCP_PROTOCOL_VERSION

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
    from src.adapters.scheduler.factory import get_scheduler_store

    scheduler = AsyncIOScheduler(timezone="UTC")
    store = get_scheduler_store()
    store.bind(scheduler)
    scheduler.start()

    logger.info(
        "context_hub_startup",
        env=settings.app_env,
        llm_provider=settings.llm_provider,
        scheduler_backend=type(store).__name__,
    )

    yield

    # Graceful shutdown: wait for running jobs before stopping.
    # try/finally guarantees store.shutdown is called even if scheduler.shutdown raises.
    try:
        scheduler.shutdown(wait=True)
    finally:
        await store.shutdown(graceful=True)
    logger.info("context_hub_shutdown")


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
            "server_version": "0.1.0",
        }

    return app


app = create_app()
