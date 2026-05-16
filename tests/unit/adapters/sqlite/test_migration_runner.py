"""Tests for SqliteMigrationRunner.

Covers:
- upgrade() applies 001_init.sql and creates schema_migrations entry
- upgrade() is idempotent (safe to call multiple times)
- current_revision() returns None before any migration, "001" after
- downgrade() raises NotImplementedError
- upgrade() with explicit target applies only up to that revision
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from context_hub.adapters.sqlite.migration_runner import SqliteMigrationRunner


@pytest.mark.asyncio
class TestSqliteMigrationRunner:
    async def test_current_revision_is_none_before_upgrade(
        self, tmp_path: Path
    ) -> None:
        db_path = str(tmp_path / "test.db")
        runner = SqliteMigrationRunner(db_path=db_path)
        rev = await runner.current_revision()
        assert rev is None

    async def test_upgrade_applies_init_migration(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = SqliteMigrationRunner(db_path=db_path)
        await runner.upgrade()
        rev = await runner.current_revision()
        assert rev == "001"

    async def test_upgrade_creates_projects_table(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = SqliteMigrationRunner(db_path=db_path)
        await runner.upgrade()
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
        ).fetchone()
        conn.close()
        assert row is not None

    async def test_upgrade_creates_documents_table(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = SqliteMigrationRunner(db_path=db_path)
        await runner.upgrade()
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
        ).fetchone()
        conn.close()
        assert row is not None

    async def test_upgrade_is_idempotent(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = SqliteMigrationRunner(db_path=db_path)
        await runner.upgrade()
        await runner.upgrade()  # second call must not raise
        rev = await runner.current_revision()
        assert rev == "001"

    async def test_downgrade_raises_not_implemented(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = SqliteMigrationRunner(db_path=db_path)
        with pytest.raises(NotImplementedError, match="downgrade"):
            await runner.downgrade("000")

    async def test_upgrade_with_empty_schema_dir(self, tmp_path: Path) -> None:
        """upgrade() with no SQL files is a safe no-op."""
        db_path = str(tmp_path / "test.db")
        empty_dir = tmp_path / "empty_schema"
        empty_dir.mkdir()
        runner = SqliteMigrationRunner(db_path=db_path, schema_dir=empty_dir)
        await runner.upgrade()  # must not raise
        rev = await runner.current_revision()
        assert rev is None

    async def test_upgrade_with_nonexistent_schema_dir(
        self, tmp_path: Path
    ) -> None:
        """upgrade() with missing schema_dir is a safe no-op."""
        db_path = str(tmp_path / "test.db")
        runner = SqliteMigrationRunner(
            db_path=db_path,
            schema_dir=tmp_path / "does_not_exist",
        )
        await runner.upgrade()  # must not raise

    async def test_upgrade_with_explicit_target(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = SqliteMigrationRunner(db_path=db_path)
        await runner.upgrade(target="001")
        rev = await runner.current_revision()
        assert rev == "001"

    async def test_upgrade_with_target_000_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        """Target "000" is before the earliest migration ("001"), so no files match."""
        db_path = str(tmp_path / "test.db")
        runner = SqliteMigrationRunner(db_path=db_path)
        with pytest.raises(ValueError):
            await runner.upgrade(target="000")

    async def test_satisfies_migration_runner_protocol(
        self, tmp_path: Path
    ) -> None:
        from context_hub.core.migration import MigrationRunner
        runner = SqliteMigrationRunner(db_path=str(tmp_path / "proto.db"))
        assert isinstance(runner, MigrationRunner)
