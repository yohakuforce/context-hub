"""Dependency-injection profiles for Context-Hub backends.

Three built-in profiles are provided:

- quickstart  : SQLite + in-memory DB (zero external dependencies, local dev)
- personal    : SQLite + persistent file DB (single-user, no Postgres needed)
- production  : PostgreSQL + pgvector + BGE-M3 embedding (full feature set)

Usage (application entrypoint)::

    from src.profiles import build_profile, BackendProfile
    profile = build_profile(os.environ.get("CH_PROFILE", "quickstart"))

The BackendProfile dataclass is intentionally simple: it holds only factory
functions so that the rest of the application depends on Protocols, not on
concrete classes.

SQLite profiles use a file path for the database.  The default paths are:

- quickstart : ":memory:" (ephemeral, for local testing)
- personal   : "~/.context_hub/context_hub.db" (persistent single-user DB)

Override the path via the ``CH_SQLITE_DB`` environment variable.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.document.repository import DocumentRepository
from src.domain.ingestion.repository import IngestionJobRepository
from src.domain.issue.repository import IssueRepository
from src.domain.project.repository import ProjectRepository

# ---------------------------------------------------------------------------
# SQLite DB path resolution
# ---------------------------------------------------------------------------

_DEFAULT_PERSONAL_DB: Path = Path.home() / ".context_hub" / "context_hub.db"


def _sqlite_db_path(default: str) -> str:
    """Resolve the SQLite database path from the environment or use *default*.

    Args:
        default: Fallback path string when ``CH_SQLITE_DB`` is not set.

    Returns:
        Resolved database path string.
    """
    return os.environ.get("CH_SQLITE_DB", default)


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
# SQLite profile factories (Phase 2 — T-20260516-004)
# ---------------------------------------------------------------------------


def _sqlite_project_repo(db_path: str) -> Callable[[AsyncSession | None], ProjectRepository]:
    """Return a factory closure for SqliteProjectRepository.

    Args:
        db_path: SQLite database file path.

    Returns:
        Factory function compatible with BackendProfile.make_project_repo.
    """
    def factory(_session: AsyncSession | None) -> ProjectRepository:
        from src.adapters.sqlite.project_repository import SqliteProjectRepository
        return SqliteProjectRepository(db_path)
    return factory


def _sqlite_document_repo(db_path: str) -> Callable[[AsyncSession | None], DocumentRepository]:
    """Return a factory closure for SqliteDocumentRepository.

    Args:
        db_path: SQLite database file path.

    Returns:
        Factory function compatible with BackendProfile.make_document_repo.
    """
    def factory(_session: AsyncSession | None) -> DocumentRepository:
        from src.adapters.sqlite.document_repository import SqliteDocumentRepository
        return SqliteDocumentRepository(db_path)
    return factory


def _sqlite_issue_repo(db_path: str) -> Callable[[AsyncSession | None], IssueRepository]:
    """Return a factory closure for SqliteIssueRepository.

    Args:
        db_path: SQLite database file path.

    Returns:
        Factory function compatible with BackendProfile.make_issue_repo.
    """
    def factory(_session: AsyncSession | None) -> IssueRepository:
        from src.adapters.sqlite.issue_repository import SqliteIssueRepository
        return SqliteIssueRepository(db_path)
    return factory


def _sqlite_job_repo(db_path: str) -> Callable[[AsyncSession | None], IngestionJobRepository]:
    """Return a factory closure for SqliteIngestionJobRepository.

    Args:
        db_path: SQLite database file path.

    Returns:
        Factory function compatible with BackendProfile.make_job_repo.
    """
    def factory(_session: AsyncSession | None) -> IngestionJobRepository:
        from src.adapters.sqlite.ingestion_job_repository import SqliteIngestionJobRepository
        return SqliteIngestionJobRepository(db_path)
    return factory


def _make_sqlite_profile(name: str, db_path: str) -> BackendProfile:
    """Construct a BackendProfile backed by SQLite at *db_path*.

    Args:
        name:    Profile name string.
        db_path: SQLite database file path (":memory:" for ephemeral).

    Returns:
        Fully wired BackendProfile using SQLite repositories.
    """
    return BackendProfile(
        name=name,
        make_project_repo=_sqlite_project_repo(db_path),
        make_document_repo=_sqlite_document_repo(db_path),
        make_issue_repo=_sqlite_issue_repo(db_path),
        make_job_repo=_sqlite_job_repo(db_path),
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

QUICKSTART_PROFILE = _make_sqlite_profile(
    name="quickstart",
    db_path=_sqlite_db_path(":memory:"),
)

PERSONAL_PROFILE = _make_sqlite_profile(
    name="personal",
    db_path=_sqlite_db_path(str(_DEFAULT_PERSONAL_DB)),
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
