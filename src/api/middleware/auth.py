"""API key authentication middleware.

All endpoints require X-Api-Key header.
Key format: ctx-hub-<consumer_id>-<random_secret>

Authentication flow:
1. Extract X-Api-Key header
2. Parse consumer_id prefix
3. Look up Consumer by id in DB
4. bcrypt.verify(plain_key, stored_hash)
5. Check Permission for requested scope + project

This module provides FastAPI Depends factories used by routers.

Development note
----------------
When APP_ENV=development (default), the environment variable DEV_API_KEY is
read at startup.  If set, requests carrying that key are granted full ADMIN
access so that local development and unit tests work without a real database.

DEV_API_KEY is NEVER checked in production (APP_ENV=production).  If you are
running in production and accidentally set DEV_API_KEY, it is silently ignored.
"""

from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException, status

from src.shared.types import Scope

# Read once at import time.  None when unset or when not in development.
_APP_ENV: str = os.environ.get("APP_ENV", "development")
_DEV_API_KEY: str | None = (
    os.environ.get("DEV_API_KEY") if _APP_ENV == "development" else None
)


class AuthenticatedConsumer:
    """Holds the verified consumer identity after auth passes."""

    def __init__(self, consumer_id: str, scopes: frozenset[Scope]) -> None:
        self.consumer_id = consumer_id
        self.scopes = scopes

    def has_scope(self, scope: Scope) -> bool:
        return scope in self.scopes or Scope.ADMIN in self.scopes


async def get_current_consumer(
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
) -> AuthenticatedConsumer:
    """FastAPI dependency: authenticate the request via X-Api-Key header.

    In development (APP_ENV=development), requests with the DEV_API_KEY
    environment variable value are granted full ADMIN scope without a DB
    lookup.  DEV_API_KEY is never accepted in production.

    TODO (Step 2): Wire to ConsumerRepository + bcrypt verification for
    production-grade authentication.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "X-Api-Key header is required."},
        )

    # Development-only shortcut: accept DEV_API_KEY from the environment.
    # _DEV_API_KEY is None when APP_ENV != "development" or when the variable
    # is not set, so this branch is structurally unreachable in production.
    if _DEV_API_KEY is not None and x_api_key == _DEV_API_KEY:
        return AuthenticatedConsumer(
            consumer_id="dev",
            scopes=frozenset({Scope.READ, Scope.WRITE, Scope.ADMIN}),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHORIZED", "message": "Invalid API key."},
    )


def require_scope(required_scope: Scope):
    """Factory for scope-checking FastAPI dependencies.

    Usage:
        @router.get("/...", ...)
        async def endpoint(_consumer=Depends(require_scope(Scope.READ))):
            ...
    """

    async def _check(
        consumer: AuthenticatedConsumer = Depends(get_current_consumer),
    ) -> AuthenticatedConsumer:
        if not consumer.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Scope '{required_scope}' is required.",
                },
            )
        return consumer

    return _check
