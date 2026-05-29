"""Lock test: REST repository providers must be profile-aware.

Regression guard for the bug where every REST read against a SQLite DB
returned 500 because the dependency providers always bound the Postgres
SQLAlchemy ORM repos — whose model SELECTs columns the SQLite migrate
schema lacks (e.g. issues.embedding). SQLite profiles must use the plain
sqlite3 adapters that match `context-hub migrate` and the MCP read path.

These tests run against the real wiring (no dependency_overrides), which is
exactly the layer the integration suite skips.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import context_hub.api.dependencies as deps
from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
from context_hub.adapters.sqlite.ingestion_job_repository import (
    SqliteIngestionJobRepository,
)
from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
from context_hub.infrastructure.db.document_repository import PostgresDocumentRepository
from context_hub.infrastructure.db.ingestion_job_repository import (
    PostgresIngestionJobRepository,
)
from context_hub.infrastructure.db.issue_repository import PostgresIssueRepository
from context_hub.infrastructure.db.project_repository import PostgresProjectRepository


@dataclass
class _StubSettings:
    database_url: str
    ch_sqlite_db: str = "./data/context_hub.db"


def _patch_profile(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setattr(
        deps, "get_profile_settings", lambda: _StubSettings(database_url=database_url)
    )


_PROVIDERS = [
    (deps.get_project_repo, SqliteProjectRepository, PostgresProjectRepository),
    (deps.get_document_repo, SqliteDocumentRepository, PostgresDocumentRepository),
    (deps.get_issue_repo, SqliteIssueRepository, PostgresIssueRepository),
    (deps.get_job_repo, SqliteIngestionJobRepository, PostgresIngestionJobRepository),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,sqlite_cls,_pg_cls", _PROVIDERS)
async def test_sqlite_profile_uses_sqlite_repo(
    monkeypatch: pytest.MonkeyPatch, provider, sqlite_cls, _pg_cls
) -> None:
    _patch_profile(monkeypatch, "sqlite+aiosqlite:///./data/context_hub.db")
    # session is ignored on the SQLite branch.
    repo = await provider(session=object())
    assert isinstance(repo, sqlite_cls)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,_sqlite_cls,pg_cls", _PROVIDERS)
async def test_postgres_profile_uses_postgres_repo(
    monkeypatch: pytest.MonkeyPatch, provider, _sqlite_cls, pg_cls
) -> None:
    _patch_profile(monkeypatch, "postgresql+asyncpg://u:p@localhost:5432/db")
    sentinel_session = object()
    repo = await provider(session=sentinel_session)
    assert isinstance(repo, pg_cls)
