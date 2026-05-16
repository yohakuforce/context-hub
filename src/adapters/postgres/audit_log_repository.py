"""PostgreSQL implementation of AuditLogRepository (append-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.audit.entities import AuditLog, OperationType
from src.domain.audit.repository import AuditLogRepository
from src.infrastructure.db.models import AuditLogRow
from src.shared.types import AuditLogId, ConsumerId, ProjectId


class PostgresAuditLogRepository(AuditLogRepository):
    """Append-only audit log repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, log: AuditLog) -> None:
        row = AuditLogRow(
            id=str(log.id),
            operation_type=log.operation_type.value,
            consumer_id=str(log.consumer_id) if log.consumer_id else None,
            project_id=str(log.project_id) if log.project_id else None,
            resource_id=log.resource_id,
            metadata_=log.metadata,
            occurred_at=log.occurred_at,
        )
        self._session.add(row)

    async def find_by_consumer(
        self,
        consumer_id: ConsumerId,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        result = await self._session.execute(
            select(AuditLogRow)
            .where(AuditLogRow.consumer_id == str(consumer_id))
            .order_by(AuditLogRow.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_row_to_domain(r) for r in result.scalars().all()]

    async def find_by_project(
        self,
        project_id: ProjectId,
        operation_type: Optional[OperationType] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        q = (
            select(AuditLogRow)
            .where(AuditLogRow.project_id == str(project_id))
            .order_by(AuditLogRow.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if operation_type:
            q = q.where(AuditLogRow.operation_type == operation_type.value)
        if since:
            q = q.where(AuditLogRow.occurred_at >= since)
        result = await self._session.execute(q)
        return [_row_to_domain(r) for r in result.scalars().all()]


def _row_to_domain(row: AuditLogRow) -> AuditLog:
    return AuditLog(
        id=AuditLogId(row.id),
        operation_type=OperationType(row.operation_type),
        consumer_id=ConsumerId(row.consumer_id) if row.consumer_id else None,
        project_id=ProjectId(row.project_id) if row.project_id else None,
        resource_id=row.resource_id,
        metadata=row.metadata_ or {},
        occurred_at=row.occurred_at,
    )
