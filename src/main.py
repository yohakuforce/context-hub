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

    # Graceful shutdown: wait for running jobs before stopping
    scheduler.shutdown(wait=True)
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else [],
        allow_credentials=True,
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
    @app.get("/health", tags=["ops"])
    async def health() -> dict:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
