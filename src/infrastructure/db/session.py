"""Async SQLAlchemy session factory.

Usage (FastAPI dependency injection):
    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session() as session:
            yield session
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

# Engine is created once at module load.
# Lazy connect: the actual DB connection is deferred until first query.
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a transactional AsyncSession per request."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
