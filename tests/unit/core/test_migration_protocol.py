"""Tests for core.migration — MigrationRunner Protocol."""

from __future__ import annotations

import pytest

from context_hub.core.migration import MigrationRunner


# ---------------------------------------------------------------------------
# Minimal conforming implementation
# ---------------------------------------------------------------------------


class _MinimalRunner:
    async def upgrade(self, target: str = "head") -> None:
        pass

    async def downgrade(self, target: str) -> None:
        pass

    async def current_revision(self) -> str | None:
        return None


class _MissingCurrentRevision:
    async def upgrade(self, target: str = "head") -> None:
        pass

    async def downgrade(self, target: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMigrationRunnerProtocol:
    def test_minimal_satisfies_protocol(self):
        runner = _MinimalRunner()
        assert isinstance(runner, MigrationRunner)

    def test_missing_method_fails(self):
        runner = _MissingCurrentRevision()
        assert not isinstance(runner, MigrationRunner)

    def test_plain_object_fails(self):
        assert not isinstance(object(), MigrationRunner)
