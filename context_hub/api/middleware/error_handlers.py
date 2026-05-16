"""Global exception handlers for FastAPI.

All unhandled exceptions are caught here and formatted as the standard
ApiResponse error envelope defined in 02-api-spec.md.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


def register_error_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app."""

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": "The requested resource was not found.",
                    "details": {},
                },
            },
        )

    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", path=request.url.path, exc=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. See server logs for details.",
                    "details": {},
                },
            },
        )
