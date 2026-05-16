"""SQLite implementation of ProjectRepository.

Uses plain sqlite3 (via asyncio.to_thread()) rather than SQLAlchemy ORM,
keeping the SQLite adapter dependency-free from Postgres-specific libraries.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime
from typing import Any, cast

from src.adapters.sqlite.session import open_connection
from src.domain.project.entities import EncryptedCredentials, Project, SourceConfig
from src.domain.project.repository import ProjectRepository
from src.shared.types import ProjectId, SourceType


class SqliteProjectRepository(ProjectRepository):
    """Concrete ProjectRepository backed by SQLite.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def find_by_id(self, project_id: ProjectId) -> Project | None:
        """Return the Project with the given ID, or None if not found.

        Args:
            project_id: UUID string identifying the project.

        Returns:
            Project domain object, or None.
        """
        row = await asyncio.to_thread(self._sync_find_by_id, str(project_id))
        return _row_to_domain(row) if row else None

    async def find_all(self) -> list[Project]:
        """Return all Projects.

        Returns:
            List of Project domain objects.
        """
        rows = await asyncio.to_thread(self._sync_find_all)
        return [_row_to_domain(r) for r in rows]

    async def find_by_external_id(
        self, external_project_id: str
    ) -> Project | None:
        """Return the Project linked to the given external ID, or None.

        Args:
            external_project_id: External system project identifier.

        Returns:
            Project domain object, or None.
        """
        row = await asyncio.to_thread(
            self._sync_find_by_external_id, external_project_id
        )
        return _row_to_domain(row) if row else None

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def save(self, project: Project) -> Project:
        """Persist a Project (insert or update). Returns the saved instance.

        Args:
            project: Project domain object to persist.

        Returns:
            The same Project instance (unchanged).
        """
        await asyncio.to_thread(self._sync_save, project)
        return project

    async def delete(self, project_id: ProjectId) -> None:
        """Delete a Project by ID.

        Args:
            project_id: UUID string identifying the project to delete.
        """
        await asyncio.to_thread(self._sync_delete, str(project_id))

    # ------------------------------------------------------------------
    # Synchronous helpers
    # ------------------------------------------------------------------

    def _sync_find_by_id(self, project_id: str) -> sqlite3.Row | None:
        with open_connection(self._db_path) as conn:
            return cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT id, name, external_project_id, sources, created_at, updated_at "
                    "FROM projects WHERE id = ?",
                    (project_id,),
                ).fetchone(),
            )

    def _sync_find_all(self) -> list[sqlite3.Row]:
        with open_connection(self._db_path) as conn:
            return conn.execute(
                "SELECT id, name, external_project_id, sources, created_at, updated_at "
                "FROM projects ORDER BY created_at DESC"
            ).fetchall()

    def _sync_find_by_external_id(self, external_id: str) -> sqlite3.Row | None:
        with open_connection(self._db_path) as conn:
            return cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT id, name, external_project_id, sources, created_at, updated_at "
                    "FROM projects WHERE external_project_id = ?",
                    (external_id,),
                ).fetchone(),
            )

    def _sync_save(self, project: Project) -> None:
        with open_connection(self._db_path) as conn:
            conn.execute(
                "INSERT INTO projects (id, name, external_project_id, sources, "
                "    created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "    name = excluded.name, "
                "    external_project_id = excluded.external_project_id, "
                "    sources = excluded.sources, "
                "    updated_at = excluded.updated_at",
                (
                    str(project.id),
                    project.name,
                    project.external_project_id,
                    json.dumps(_sources_to_json(project.sources)),
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
            conn.commit()

    def _sync_delete(self, project_id: str) -> None:
        with open_connection(self._db_path) as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _sources_to_json(sources: list[SourceConfig]) -> list[dict[str, Any]]:
    result = []
    for s in sources:
        entry: dict[str, Any] = {
            "source_type": s.source_type.value,
            "sync_interval_minutes": s.sync_interval_minutes,
            "is_enabled": s.is_enabled,
            "channel_ids": list(s.channel_ids),
            "backlog_project_key": s.backlog_project_key,
            "redmine_project_identifier": s.redmine_project_identifier,
        }
        if s.credentials:
            entry["credentials"] = {
                "encrypted_value": s.credentials.encrypted_value,
                "algorithm": s.credentials.algorithm,
                "encrypted_at": s.credentials.encrypted_at.isoformat(),
            }
        result.append(entry)
    return result


def _json_to_source(data: dict[str, Any]) -> SourceConfig:
    creds = None
    if "credentials" in data and data["credentials"]:
        c = data["credentials"]
        creds = EncryptedCredentials(
            encrypted_value=c["encrypted_value"],
            algorithm=c["algorithm"],
            encrypted_at=datetime.fromisoformat(c["encrypted_at"]),
        )
    return SourceConfig(
        source_type=SourceType(data["source_type"]),
        sync_interval_minutes=data["sync_interval_minutes"],
        is_enabled=data["is_enabled"],
        credentials=creds,
        channel_ids=tuple(data.get("channel_ids", [])),
        backlog_project_key=data.get("backlog_project_key"),
        redmine_project_identifier=data.get("redmine_project_identifier"),
    )


def _row_to_domain(row: sqlite3.Row) -> Project:
    row_id, name, external_project_id, sources_json, created_at, updated_at = row
    sources_raw: list[dict[str, Any]] = json.loads(sources_json or "[]")
    return Project(
        id=ProjectId(row_id),
        name=name,
        external_project_id=external_project_id,
        sources=[_json_to_source(s) for s in sources_raw],
        created_at=datetime.fromisoformat(created_at),
        updated_at=datetime.fromisoformat(updated_at),
    )
