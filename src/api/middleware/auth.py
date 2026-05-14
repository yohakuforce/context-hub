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
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from src.shared.types import Scope


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

    TODO (Step 2): Wire to ConsumerRepository + bcrypt verification.
    Currently returns a stub consumer for skeleton testing.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "X-Api-Key header is required."},
        )

    # --- STUB: replace with real DB lookup + bcrypt.checkpw in Step 2 ---
    # This allows the router skeleton to function without a DB connection.
    if x_api_key == "ctx-hub-dev-stub":
        return AuthenticatedConsumer(
            consumer_id="dev-stub",
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
