"""Tests for SqliteProjectRepository.

Uses a temporary file-backed SQLite database.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
import sqlite_vec

from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
from context_hub.domain.project.entities import Project
from context_hub.shared.types import ProjectId, SourceType, new_id


def _make_project(name: str = "Test Project") -> Project:
    return Project(
        id=ProjectId(new_id()),
        name=name,
        external_project_id=None,
        sources=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "proj_test.db")
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    schema = (
        Path(__file__).parent.parent.parent.parent.parent
        / "context_hub" / "_sqlite_schema" / "001_init.sql"
    )
    conn.executescript(schema.read_text(encoding="utf-8"))
    conn.close()
    return path


@pytest.mark.asyncio
class TestSqliteProjectRepository:
    async def test_find_by_id_returns_none_when_missing(
        self, db_path: str
    ) -> None:
        repo = SqliteProjectRepository(db_path)
        result = await repo.find_by_id(ProjectId(new_id()))
        assert result is None

    async def test_save_and_find_by_id(self, db_path: str) -> None:
        repo = SqliteProjectRepository(db_path)
        project = _make_project("My Project")
        await repo.save(project)
        found = await repo.find_by_id(project.id)
        assert found is not None
        assert found.id == project.id
        assert found.name == "My Project"

    async def test_find_all_returns_saved_projects(self, db_path: str) -> None:
        repo = SqliteProjectRepository(db_path)
        p1 = _make_project("Project A")
        p2 = _make_project("Project B")
        await repo.save(p1)
        await repo.save(p2)
        all_projects = await repo.find_all()
        ids = [p.id for p in all_projects]
        assert p1.id in ids
        assert p2.id in ids

    async def test_find_all_empty_returns_empty_list(self, db_path: str) -> None:
        repo = SqliteProjectRepository(db_path)
        result = await repo.find_all()
        assert result == []

    async def test_save_is_upsert(self, db_path: str) -> None:
        repo = SqliteProjectRepository(db_path)
        project = _make_project("Original Name")
        await repo.save(project)
        updated = Project(
            id=project.id,
            name="Updated Name",
            external_project_id=None,
            sources=[],
            created_at=project.created_at,
            updated_at=datetime.utcnow(),
        )
        await repo.save(updated)
        found = await repo.find_by_id(project.id)
        assert found is not None
        assert found.name == "Updated Name"

    async def test_find_by_external_id_returns_none_when_missing(
        self, db_path: str
    ) -> None:
        repo = SqliteProjectRepository(db_path)
        result = await repo.find_by_external_id("ext-999")
        assert result is None

    async def test_find_by_external_id_returns_project(
        self, db_path: str
    ) -> None:
        repo = SqliteProjectRepository(db_path)
        project = Project(
            id=ProjectId(new_id()),
            name="External Project",
            external_project_id="EXT-001",
            sources=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        await repo.save(project)
        found = await repo.find_by_external_id("EXT-001")
        assert found is not None
        assert found.id == project.id

    async def test_delete_removes_project(self, db_path: str) -> None:
        repo = SqliteProjectRepository(db_path)
        project = _make_project()
        await repo.save(project)
        await repo.delete(project.id)
        found = await repo.find_by_id(project.id)
        assert found is None

    async def test_delete_nonexistent_is_noop(self, db_path: str) -> None:
        repo = SqliteProjectRepository(db_path)
        await repo.delete(ProjectId(new_id()))  # must not raise
