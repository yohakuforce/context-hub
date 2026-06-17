"""Integration tests for the inbox folder watcher.

Verifies polling-mode auto-ingest: drop a file into the inbox tree →
``scan_inbox`` upserts it as a Document; re-running with unchanged content
is a no-op; editing the file produces an update.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from context_hub.domain.project.entities import Project
from context_hub.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter
from context_hub.services.inbox_watcher import scan_inbox
from context_hub.shared.types import ProjectId, SourceType

from tests.integration.test_api_routers import InMemoryProjectRepository
from tests.integration.test_ingestion_service import InMemoryDocumentRepository


def _make_project(pid: str = "proj-inbox") -> Project:
    return Project(
        id=ProjectId(pid),
        name="Inbox Test Project",
        external_project_id="PROJ-INBOX",
        sources=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    root = tmp_path / "inbox"
    (root / "meeting").mkdir(parents=True)
    (root / "file").mkdir(parents=True)
    (root / "email").mkdir(parents=True)
    return root


@pytest.fixture
def deps():
    project_repo = InMemoryProjectRepository()
    doc_repo = InMemoryDocumentRepository()
    embedding = MockEmbeddingAdapter()
    return project_repo, doc_repo, embedding


class TestInboxScanBasic:
    @pytest.mark.asyncio
    async def test_ingests_new_markdown_file(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        (inbox / "meeting" / "2026-05-20-weekly.md").write_text(
            "# Weekly\n\nDecision: ship plan A.", encoding="utf-8"
        )

        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result.ingested == ["meeting/2026-05-20-weekly.md"]
        assert result.updated == []
        assert result.skipped == []
        assert result.errors == []

        stored = await doc_repo.find_by_external_id(
            ProjectId("proj-inbox"),
            SourceType.MEETING,
            "meeting/2026-05-20-weekly.md",
        )
        assert stored is not None
        assert "Decision: ship plan A." in stored.raw_content.text
        assert stored.is_embedded is True

    @pytest.mark.asyncio
    async def test_unchanged_file_is_skipped_on_second_scan(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        (inbox / "meeting" / "note.md").write_text("# Note\n\nbody", encoding="utf-8")

        await scan_inbox(inbox, project_repo, doc_repo, embedding)
        result2 = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result2.ingested == []
        assert result2.updated == []
        assert result2.skipped == ["meeting/note.md"]

    @pytest.mark.asyncio
    async def test_edited_file_is_upserted(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        path = inbox / "meeting" / "note.md"
        path.write_text("# Note\n\nv1", encoding="utf-8")
        await scan_inbox(inbox, project_repo, doc_repo, embedding)

        path.write_text("# Note\n\nv2 updated", encoding="utf-8")
        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result.ingested == []
        assert result.updated == ["meeting/note.md"]
        stored = await doc_repo.find_by_external_id(
            ProjectId("proj-inbox"), SourceType.MEETING, "meeting/note.md"
        )
        assert "v2 updated" in stored.raw_content.text


class TestInboxScanRoutingAndFilters:
    @pytest.mark.asyncio
    async def test_routes_each_subdir_to_correct_source_type(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        (inbox / "meeting" / "m.md").write_text("m", encoding="utf-8")
        (inbox / "file" / "f.md").write_text("f", encoding="utf-8")
        (inbox / "email" / "e.txt").write_text("e", encoding="utf-8")

        await scan_inbox(inbox, project_repo, doc_repo, embedding)

        for ext_id, src in [
            ("meeting/m.md", SourceType.MEETING),
            ("file/f.md", SourceType.FILE),
            ("email/e.txt", SourceType.EMAIL),
        ]:
            assert await doc_repo.find_by_external_id(
                ProjectId("proj-inbox"), src, ext_id
            ) is not None

    @pytest.mark.asyncio
    async def test_doc_subdir_ingested_as_file_and_scanned_first(self, inbox, deps):
        """doc/ holds synthesized/converted markdown — ingested as FILE, embedded
        before the raw long tail so high-value docs surface first on slow CPUs."""
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        (inbox / "doc").mkdir(parents=True)
        (inbox / "doc" / "glossary.md").write_text("# Glossary\n\nterms", encoding="utf-8")
        (inbox / "file" / "f.md").write_text("f", encoding="utf-8")

        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        # doc/ routes to SourceType.FILE under its own external_id namespace.
        assert await doc_repo.find_by_external_id(
            ProjectId("proj-inbox"), SourceType.FILE, "doc/glossary.md"
        ) is not None
        # doc/ is scanned before file/ (priority ordering).
        assert result.ingested.index("doc/glossary.md") < result.ingested.index("file/f.md")

    @pytest.mark.asyncio
    async def test_ignores_unsupported_extensions(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        (inbox / "meeting" / "binary.pdf").write_text("%PDF-bytes", encoding="utf-8")
        (inbox / "meeting" / "slides.pptx").write_text("zipbytes", encoding="utf-8")
        (inbox / "meeting" / "ok.md").write_text("# ok\n\nbody", encoding="utf-8")

        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result.ingested == ["meeting/ok.md"]
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_ignores_hidden_files_and_unknown_subdirs(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        (inbox / "meeting" / ".DS_Store").write_text("noise", encoding="utf-8")
        (inbox / "meeting" / "real.md").write_text("real", encoding="utf-8")
        (inbox / "random-extra-dir").mkdir()
        (inbox / "random-extra-dir" / "x.md").write_text("x", encoding="utf-8")

        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result.ingested == ["meeting/real.md"]

    @pytest.mark.asyncio
    async def test_nested_subdirectories_are_included(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        nested = inbox / "meeting" / "2026" / "may"
        nested.mkdir(parents=True)
        (nested / "20-weekly.md").write_text("# Weekly\n\nbody", encoding="utf-8")

        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result.ingested == ["meeting/2026/may/20-weekly.md"]

    @pytest.mark.asyncio
    async def test_empty_file_is_skipped(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        (inbox / "meeting" / "empty.md").write_text("", encoding="utf-8")

        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result.ingested == []
        assert result.skipped == ["meeting/empty.md"]


class TestInboxScanTitleExtraction:
    @pytest.mark.asyncio
    async def test_uses_first_h1_as_title(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        (inbox / "meeting" / "with-h1.md").write_text(
            "# 2026-05-20 Weekly Sync\n\nbody here", encoding="utf-8"
        )

        await scan_inbox(inbox, project_repo, doc_repo, embedding)

        stored = await doc_repo.find_by_external_id(
            ProjectId("proj-inbox"), SourceType.MEETING, "meeting/with-h1.md"
        )
        assert stored.raw_content.text.startswith("# 2026-05-20 Weekly Sync")

    @pytest.mark.asyncio
    async def test_falls_back_to_filename_when_no_h1(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        (inbox / "file" / "plain.txt").write_text("just text", encoding="utf-8")

        await scan_inbox(inbox, project_repo, doc_repo, embedding)

        stored = await doc_repo.find_by_external_id(
            ProjectId("proj-inbox"), SourceType.FILE, "file/plain.txt"
        )
        assert stored.raw_content.text.startswith("# plain\n")


class TestInboxScanProjectResolution:
    @pytest.mark.asyncio
    async def test_uses_single_project_when_one_exists(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project("proj-alpha"))
        (inbox / "meeting" / "n.md").write_text("body", encoding="utf-8")

        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result.ingested == ["meeting/n.md"]
        stored = await doc_repo.find_by_external_id(
            ProjectId("proj-alpha"), SourceType.MEETING, "meeting/n.md"
        )
        assert stored is not None

    @pytest.mark.asyncio
    async def test_skips_when_no_projects_exist(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        (inbox / "meeting" / "n.md").write_text("body", encoding="utf-8")

        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result.ingested == []

    @pytest.mark.asyncio
    async def test_skips_when_multiple_projects_and_no_env(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project("proj-a"))
        await project_repo.save(_make_project("proj-b"))
        (inbox / "meeting" / "n.md").write_text("body", encoding="utf-8")

        result = await scan_inbox(inbox, project_repo, doc_repo, embedding)

        assert result.ingested == []

    @pytest.mark.asyncio
    async def test_explicit_project_id_disambiguates(self, inbox, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project("proj-a"))
        await project_repo.save(_make_project("proj-b"))
        (inbox / "meeting" / "n.md").write_text("body", encoding="utf-8")

        result = await scan_inbox(
            inbox, project_repo, doc_repo, embedding,
            configured_project_id="proj-b",
        )

        assert result.ingested == ["meeting/n.md"]
        stored = await doc_repo.find_by_external_id(
            ProjectId("proj-b"), SourceType.MEETING, "meeting/n.md"
        )
        assert stored is not None


class TestInboxScanRobustness:
    @pytest.mark.asyncio
    async def test_missing_inbox_dir_is_noop(self, tmp_path, deps):
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())

        result = await scan_inbox(
            tmp_path / "does-not-exist", project_repo, doc_repo, embedding
        )

        assert result.ingested == []
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_partial_inbox_layout_works(self, tmp_path, deps):
        """Only 'meeting/' exists, no 'file/' or 'email/' subdirs — still ingests."""
        project_repo, doc_repo, embedding = deps
        await project_repo.save(_make_project())
        root = tmp_path / "inbox"
        (root / "meeting").mkdir(parents=True)
        (root / "meeting" / "n.md").write_text("body", encoding="utf-8")

        result = await scan_inbox(root, project_repo, doc_repo, embedding)

        assert result.ingested == ["meeting/n.md"]
