"""Async SQLAlchemy session factory.

The engine and session factory are created lazily on first access. Import-time
construction is avoided so that the SQLAlchemy dialect (e.g. asyncpg, aiosqlite)
is loaded only when the corresponding DATABASE_URL is actually used.

Usage (FastAPI dependency injection):
    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session() as session:
            yield session
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from context_hub.config import settings


@lru_cache(maxsize=1)
def _get_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.app_env == "development",
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


@lru_cache(maxsize=1)
def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        _get_engine(),
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


def __getattr__(name: str) -> Any:
    """PEP 562 lazy attribute access for `engine` and `async_session`.

    Keeps backward compatibility for callers that imported these names
    directly (e.g. `from ...session import async_session`) while deferring
    the actual engine creation until first use.
    """
    if name == "engine":
        return _get_engine()
    if name == "async_session":
        return _get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a transactional AsyncSession per request."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
