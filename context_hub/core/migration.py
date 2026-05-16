"""MigrationRunner Protocol — backend-agnostic schema migration abstraction.

Implementations:
- Alembic runner for PostgreSQL  (Phase 1, existing)
- SQLite migration runner         (Phase 2)

Design notes:
- upgrade/downgrade mirror the Alembic CLI semantics.
- current_revision returns None when no migration has been applied (fresh DB).
- The Protocol is intentionally thin; backends own their revision schemes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MigrationRunner(Protocol):
    """Structural interface for schema migration runners."""

    async def upgrade(self, target: str = "head") -> None:
        """Apply pending migrations up to *target* revision.

        Args:
            target: Alembic-style revision identifier ("head", a hash, etc.).
        """
        ...

    async def downgrade(self, target: str) -> None:
        """Roll back migrations to *target* revision.

        Args:
            target: Revision to roll back to ("-1" for one step, a hash, etc.).
        """
        ...

    async def current_revision(self) -> str | None:
        """Return the currently applied revision identifier.

        Returns:
            Revision string, or None if the schema is unversioned.
        """
        ...
