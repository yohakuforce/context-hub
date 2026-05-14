"""Context-Hub FastAPI application entry point."""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.error_handlers import register_error_handlers
from src.api.routers import issues, projects, query, sync
from src.config import settings

logger = structlog.get_logger()


def create_app() -> FastAPI:
    """Factory function that creates and configures the FastAPI app."""
    app = FastAPI(
        title="Context-Hub API",
        description="Context collection and storage foundation for AI projects",
        version="1.0.0",
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

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info(
            "context_hub_startup",
            env=settings.app_env,
            llm_provider=settings.llm_provider,
        )

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("context_hub_shutdown")

    return app


app = create_app()
