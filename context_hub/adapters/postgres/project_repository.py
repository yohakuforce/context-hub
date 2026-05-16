"""PostgreSQL implementation of ProjectRepository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_hub.domain.project.entities import EncryptedCredentials, Project, SourceConfig
from context_hub.domain.project.repository import ProjectRepository
from context_hub.infrastructure.db.models import ProjectRow
from context_hub.shared.types import ProjectId, SourceType


class PostgresProjectRepository(ProjectRepository):
    """Concrete repository backed by PostgreSQL via SQLAlchemy AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def find_by_id(self, project_id: ProjectId) -> Optional[Project]:
        row = await self._session.get(ProjectRow, str(project_id))
        if row is None:
            return None
        return _row_to_domain(row)

    async def find_all(self) -> list[Project]:
        result = await self._session.execute(select(ProjectRow))
        return [_row_to_domain(row) for row in result.scalars().all()]

    async def find_by_external_id(self, external_project_id: str) -> Optional[Project]:
        result = await self._session.execute(
            select(ProjectRow).where(
                ProjectRow.external_project_id == external_project_id
            )
        )
        row = result.scalar_one_or_none()
        return _row_to_domain(row) if row else None

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def save(self, project: Project) -> Project:
        existing = await self._session.get(ProjectRow, str(project.id))
        if existing is None:
            row = _domain_to_row(project)
            self._session.add(row)
        else:
            existing.name = project.name
            existing.external_project_id = project.external_project_id
            existing.sources = _sources_to_json(project.sources)
            existing.updated_at = project.updated_at
        return project

    async def delete(self, project_id: ProjectId) -> None:
        row = await self._session.get(ProjectRow, str(project_id))
        if row is not None:
            await self._session.delete(row)


# ---------------------------------------------------------------------------
# Internal mapping helpers
# ---------------------------------------------------------------------------


def _domain_to_row(project: Project) -> ProjectRow:
    return ProjectRow(
        id=str(project.id),
        name=project.name,
        external_project_id=project.external_project_id,
        sources=_sources_to_json(project.sources),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _sources_to_json(sources: list[SourceConfig]) -> list[dict]:
    result = []
    for s in sources:
        entry: dict = {
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


def _row_to_domain(row: ProjectRow) -> Project:
    sources_raw: list[dict] = row.sources or []
    sources = [_json_to_source(s) for s in sources_raw]
    return Project(
        id=ProjectId(row.id),
        name=row.name,
        external_project_id=row.external_project_id,
        sources=sources,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _json_to_source(data: dict) -> SourceConfig:
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
