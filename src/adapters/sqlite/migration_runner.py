"""SQLite migration runner — lightweight schema management without Alembic.

Applies SQL migration files from the schema/sqlite/ directory in revision order.
Each revision is tracked in the schema_migrations table so migrations are
idempotent: running upgrade() multiple times is safe.

Intentionally minimal: no down-migrations are implemented for v0.1 (SQLite
databases are typically small enough to recreate if a rollback is needed).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from src.adapters.sqlite.session import open_connection

# Default path for the bundled SQLite schema files.
_SCHEMA_DIR: Path = Path(__file__).parent.parent.parent.parent / "schema" / "sqlite"

# Revision string embedded in 001_init.sql.
_INIT_REVISION: str = "001"


class SqliteMigrationRunner:
    """MigrationRunner Protocol implementation for SQLite.

    Applies plain-SQL migration files from *schema_dir*.  Each file must be
    named ``NNN_description.sql`` where NNN is a zero-padded integer revision
    number (e.g. ``001_init.sql``).

    Args:
        db_path:    Path to the SQLite database file.
        schema_dir: Directory containing SQL migration files.
                    Defaults to ``schema/sqlite/`` relative to the project root.

    Example::

        runner = SqliteMigrationRunner(db_path="context_hub.db")
        await runner.upgrade()
        rev = await runner.current_revision()
        print(rev)   # "001"
    """

    def __init__(
        self,
        db_path: str,
        schema_dir: Path | None = None,
    ) -> None:
        self._db_path = db_path
        self._schema_dir: Path = schema_dir or _SCHEMA_DIR

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    async def upgrade(self, target: str = "head") -> None:
        """Apply all pending migrations up to *target* revision.

        Args:
            target: Revision identifier to upgrade to.  "head" means the
                    latest available migration.  A numeric string (e.g. "001")
                    applies up to and including that revision.

        Raises:
            ValueError: If *target* is not "head" and no matching file exists.
            FileNotFoundError: If *schema_dir* does not exist.
        """
        migration_files = _discover_migrations(self._schema_dir)
        if not migration_files:
            return

        if target != "head":
            migration_files = [
                f for f in migration_files
                if _revision_from_path(f) <= target
            ]
            if not migration_files:
                raise ValueError(
                    f"No migration files found for target revision {target!r} "
                    f"in {self._schema_dir}"
                )

        applied = await asyncio.to_thread(self._sync_get_applied_revisions)

        for migration_path in migration_files:
            rev = _revision_from_path(migration_path)
            if rev not in applied:
                await asyncio.to_thread(
                    self._sync_apply_migration, migration_path, rev
                )

    async def downgrade(self, target: str) -> None:
        """Not implemented — SQLite databases are recreated rather than downgraded.

        Args:
            target: Unused; provided for Protocol compatibility.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "SQLite downgrade is not supported. "
            "Delete the database file and run upgrade() to recreate the schema."
        )

    async def current_revision(self) -> str | None:
        """Return the most recently applied revision, or None if unversioned.

        Returns:
            The lexicographically largest applied revision string, or None.
        """
        applied = await asyncio.to_thread(self._sync_get_applied_revisions)
        return max(applied) if applied else None

    # ------------------------------------------------------------------
    # Synchronous helpers (executed in thread pool)
    # ------------------------------------------------------------------

    def _sync_get_applied_revisions(self) -> set[str]:
        """Return the set of already-applied revision strings."""
        with open_connection(self._db_path) as conn:
            # schema_migrations table may not exist on a brand-new database.
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "    revision   TEXT PRIMARY KEY, "
                "    applied_at TEXT NOT NULL"
                ")"
            )
            conn.commit()
            rows = conn.execute(
                "SELECT revision FROM schema_migrations"
            ).fetchall()
            return {row[0] for row in rows}

    def _sync_apply_migration(self, path: Path, revision: str) -> None:
        """Execute a single SQL migration file and record its revision."""
        sql = path.read_text(encoding="utf-8")
        with open_connection(self._db_path) as conn:
            conn.executescript(sql)
            applied_at = datetime.now(tz=UTC).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (revision, applied_at) "
                "VALUES (?, ?)",
                (revision, applied_at),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _discover_migrations(schema_dir: Path) -> list[Path]:
    """Return SQL migration files sorted by revision number.

    Args:
        schema_dir: Directory to scan for ``*.sql`` files.

    Returns:
        Sorted list of Path objects; empty if the directory does not exist.
    """
    if not schema_dir.exists():
        return []
    files = sorted(schema_dir.glob("*.sql"))
    return [f for f in files if f.suffix == ".sql"]


def _revision_from_path(path: Path) -> str:
    """Extract the revision string (prefix before first underscore) from a filename.

    Args:
        path: Path to a migration SQL file (e.g. ``001_init.sql``).

    Returns:
        The leading revision number as a string (e.g. ``"001"``).
    """
    return path.stem.split("_", 1)[0]
