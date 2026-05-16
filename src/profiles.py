"""Dependency-injection profiles for Context-Hub backends.

Three built-in profiles are provided:

- quickstart  : SQLite + mock embedding (zero external dependencies, local dev)
- personal    : SQLite + real BGE-M3 embedding (single-user, no Postgres needed)
- production  : PostgreSQL + pgvector + BGE-M3 embedding (full feature set)

Usage (application entrypoint)::

    from src.profiles import build_profile, BackendProfile
    profile = build_profile(os.environ.get("CH_PROFILE", "quickstart"))

The BackendProfile dataclass is intentionally simple: it holds only factory
functions so that the rest of the application depends on Protocols, not on
concrete classes.

Phase 1 note:
    The SQLite factories are stubs — they raise NotImplementedError until
    T-20260516-004 implements the SQLite adapter.  This allows the DI wiring
    to be tested end-to-end with the Postgres profile without blocking the
    OSS launch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.document.repository import DocumentRepository
from src.domain.ingestion.repository import IngestionJobRepository
from src.domain.issue.repository import IssueRepository
from src.domain.project.repository import ProjectRepository


# ---------------------------------------------------------------------------
# Profile dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendProfile:
    """Immutable collection of repository factory functions.

    Each factory accepts an AsyncSession (or None for in-process backends)
    and returns the appropriate repository implementation.
    """

    name: str
    make_project_repo: Callable[[AsyncSession | None], ProjectRepository]
    make_document_repo: Callable[[AsyncSession | None], DocumentRepository]
    make_issue_repo: Callable[[AsyncSession | None], IssueRepository]
    make_job_repo: Callable[[AsyncSession | None], IngestionJobRepository]


# ---------------------------------------------------------------------------
# Postgres profile factories
# ---------------------------------------------------------------------------


def _postgres_project_repo(session: AsyncSession | None) -> ProjectRepository:
    if session is None:
        raise ValueError("PostgreSQL profile requires an AsyncSession")
    from src.adapters.postgres.project_repository import PostgresProjectRepository
    return PostgresProjectRepository(session)


def _postgres_document_repo(session: AsyncSession | None) -> DocumentRepository:
    if session is None:
        raise ValueError("PostgreSQL profile requires an AsyncSession")
    from src.adapters.postgres.document_repository import PostgresDocumentRepository
    return PostgresDocumentRepository(session)


def _postgres_issue_repo(session: AsyncSession | None) -> IssueRepository:
    if session is None:
        raise ValueError("PostgreSQL profile requires an AsyncSession")
    from src.adapters.postgres.issue_repository import PostgresIssueRepository
    return PostgresIssueRepository(session)


def _postgres_job_repo(session: AsyncSession | None) -> IngestionJobRepository:
    if session is None:
        raise ValueError("PostgreSQL profile requires an AsyncSession")
    from src.adapters.postgres.ingestion_job_repository import (
        PostgresIngestionJobRepository,
    )
    return PostgresIngestionJobRepository(session)


# ---------------------------------------------------------------------------
# SQLite profile factories (Phase 2 stubs)
# ---------------------------------------------------------------------------


def _sqlite_stub(_session: AsyncSession | None) -> None:  # type: ignore[return]
    raise NotImplementedError(
        "SQLite backend is not yet implemented. "
        "It will be available in T-20260516-004 (Phase 2). "
        "Use profile='production' for a fully functional backend."
    )


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------


PRODUCTION_PROFILE = BackendProfile(
    name="production",
    make_project_repo=_postgres_project_repo,
    make_document_repo=_postgres_document_repo,
    make_issue_repo=_postgres_issue_repo,
    make_job_repo=_postgres_job_repo,
)

# Aliases — quickstart / personal will resolve to SQLite once Phase 2 lands.
# For now they raise NotImplementedError so callers know what is missing.
QUICKSTART_PROFILE = BackendProfile(
    name="quickstart",
    make_project_repo=_sqlite_stub,   # type: ignore[arg-type]
    make_document_repo=_sqlite_stub,  # type: ignore[arg-type]
    make_issue_repo=_sqlite_stub,     # type: ignore[arg-type]
    make_job_repo=_sqlite_stub,       # type: ignore[arg-type]
)

PERSONAL_PROFILE = BackendProfile(
    name="personal",
    make_project_repo=_sqlite_stub,   # type: ignore[arg-type]
    make_document_repo=_sqlite_stub,  # type: ignore[arg-type]
    make_issue_repo=_sqlite_stub,     # type: ignore[arg-type]
    make_job_repo=_sqlite_stub,       # type: ignore[arg-type]
)

_PROFILES: dict[str, BackendProfile] = {
    "production": PRODUCTION_PROFILE,
    "quickstart": QUICKSTART_PROFILE,
    "personal": PERSONAL_PROFILE,
}


def build_profile(name: str) -> BackendProfile:
    """Return the named BackendProfile.

    Args:
        name: One of "quickstart", "personal", "production".

    Raises:
        ValueError: If *name* is not a recognised profile.
    """
    try:
        return _PROFILES[name]
    except KeyError:
        valid = ", ".join(sorted(_PROFILES))
        raise ValueError(
            f"Unknown backend profile {name!r}. Valid options: {valid}"
        )
