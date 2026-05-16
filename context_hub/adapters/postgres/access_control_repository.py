"""PostgreSQL implementation of ConsumerRepository and PermissionRepository."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_hub.domain.access_control.entities import Consumer, HashedApiKey, Permission
from context_hub.domain.access_control.repository import ConsumerRepository, PermissionRepository
from context_hub.infrastructure.db.models import ConsumerRow, PermissionRow
from context_hub.shared.types import ConsumerId, PermissionId, ProjectId, Scope


class PostgresConsumerRepository(ConsumerRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, consumer_id: ConsumerId) -> Optional[Consumer]:
        row = await self._session.get(ConsumerRow, str(consumer_id))
        return _consumer_row_to_domain(row) if row else None

    async def find_by_api_key_prefix(self, prefix: str) -> Optional[Consumer]:
        # The prefix is the consumer_id portion stored in the key.
        # We look up by id directly (caller provides the UUID prefix).
        result = await self._session.execute(
            select(ConsumerRow).where(ConsumerRow.id == prefix)
        )
        row = result.scalar_one_or_none()
        return _consumer_row_to_domain(row) if row else None

    async def find_all_active(self) -> list[Consumer]:
        result = await self._session.execute(
            select(ConsumerRow).where(ConsumerRow.is_active.is_(True))
        )
        return [_consumer_row_to_domain(r) for r in result.scalars().all()]

    async def save(self, consumer: Consumer) -> Consumer:
        existing = await self._session.get(ConsumerRow, str(consumer.id))
        if existing is None:
            self._session.add(_consumer_domain_to_row(consumer))
        else:
            existing.name = consumer.name
            existing.api_key_hash = consumer.hashed_api_key.hash_value
            existing.api_key_algorithm = consumer.hashed_api_key.algorithm
            existing.api_key_created_at = consumer.hashed_api_key.created_at
            existing.is_active = consumer.is_active
        return consumer


class PostgresPermissionRepository(PermissionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_consumer(self, consumer_id: ConsumerId) -> list[Permission]:
        result = await self._session.execute(
            select(PermissionRow).where(
                PermissionRow.consumer_id == str(consumer_id)
            )
        )
        return [_permission_row_to_domain(r) for r in result.scalars().all()]

    async def find_by_consumer_and_project(
        self,
        consumer_id: ConsumerId,
        project_id: ProjectId,
    ) -> Optional[Permission]:
        # Match global (project_id IS NULL) or project-specific
        result = await self._session.execute(
            select(PermissionRow).where(
                PermissionRow.consumer_id == str(consumer_id),
                PermissionRow.project_id.in_([str(project_id), None]),
            )
        )
        row = result.scalar_one_or_none()
        return _permission_row_to_domain(row) if row else None

    async def save(self, permission: Permission) -> Permission:
        existing = await self._session.get(PermissionRow, str(permission.id))
        if existing is None:
            self._session.add(_permission_domain_to_row(permission))
        else:
            existing.scopes = [s.value for s in permission.scopes]
        return permission

    async def delete(self, permission_id: PermissionId) -> None:
        row = await self._session.get(PermissionRow, str(permission_id))
        if row is not None:
            await self._session.delete(row)


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _consumer_domain_to_row(consumer: Consumer) -> ConsumerRow:
    return ConsumerRow(
        id=str(consumer.id),
        name=consumer.name,
        api_key_hash=consumer.hashed_api_key.hash_value,
        api_key_algorithm=consumer.hashed_api_key.algorithm,
        api_key_created_at=consumer.hashed_api_key.created_at,
        is_active=consumer.is_active,
        created_at=consumer.created_at,
    )


def _consumer_row_to_domain(row: ConsumerRow) -> Consumer:
    hashed_key = HashedApiKey(
        hash_value=row.api_key_hash,
        algorithm=row.api_key_algorithm,
        created_at=row.api_key_created_at,
    )
    return Consumer(
        id=ConsumerId(row.id),
        name=row.name,
        hashed_api_key=hashed_key,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def _permission_domain_to_row(permission: Permission) -> PermissionRow:
    return PermissionRow(
        id=str(permission.id),
        consumer_id=str(permission.consumer_id),
        project_id=str(permission.project_id) if permission.project_id else None,
        scopes=[s.value for s in permission.scopes],
        created_at=permission.created_at,
    )


def _permission_row_to_domain(row: PermissionRow) -> Permission:
    return Permission(
        id=PermissionId(row.id),
        consumer_id=ConsumerId(row.consumer_id),
        project_id=ProjectId(row.project_id) if row.project_id else None,
        scopes=frozenset(Scope(s) for s in (row.scopes or [])),
        created_at=row.created_at,
    )
