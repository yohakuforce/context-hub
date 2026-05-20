"""Inbox folder watcher — auto-ingest .md/.txt files dropped into a local folder.

Watches ``<inbox_dir>/{meeting,file,email}/`` on a polling interval (default 60s).
Each file is treated as one Document.

Idempotency
-----------
``external_id`` is ``"<source_type>/<relative_path>"``. Re-scans look up the
existing Document by external_id and compare the stored ``raw_content.text``
against the freshly-composed text — unchanged files are skipped, so embedding
cost stays bounded.

Editing a file in place → text differs → composite-key upsert
(project_id, source_type, external_id) replaces the prior document atomically.

Single-project assumption
-------------------------
Context-Hub is deployed 1:1 with a project. The target project is resolved by:

  1. ``settings.ch_project_id`` (env ``CH_PROJECT_ID``); else
  2. The sole project in the repo when exactly one exists.

When zero or multiple projects exist and no ``CH_PROJECT_ID`` is set, the scan
is skipped with a warning.

Accepted layout
---------------
::

    <ch_inbox_dir>/
        meeting/
            2026-05-20-weekly.md
            sub/nested-also-ok.md
        file/
            spec.md
        email/
            saved-thread.txt

Only ``.md`` and ``.txt`` are ingested. PDF / PowerPoint / docx must be
converted to Markdown by the user before being dropped in.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from context_hub.domain.document.entities import Document
from context_hub.domain.document.repository import DocumentRepository
from context_hub.domain.project.repository import ProjectRepository
from context_hub.infrastructure.embedding.base import EmbeddingProvider
from context_hub.shared.types import ProjectId, RawContent, SourceType

logger = logging.getLogger(__name__)

# Sub-directory name → SourceType
_SUBDIR_TO_SOURCE: dict[str, SourceType] = {
    "meeting": SourceType.MEETING,
    "file": SourceType.FILE,
    "email": SourceType.EMAIL,
}
_ALLOWED_EXTS = frozenset({".md", ".txt"})


class InboxScanResult:
    """Summary of one scan pass."""

    __slots__ = ("ingested", "updated", "skipped", "errors")

    def __init__(self) -> None:
        self.ingested: list[str] = []
        self.updated: list[str] = []
        self.skipped: list[str] = []
        self.errors: list[tuple[str, str]] = []

    @property
    def changed_count(self) -> int:
        return len(self.ingested) + len(self.updated)

    def as_dict(self) -> dict[str, int]:
        return {
            "ingested": len(self.ingested),
            "updated": len(self.updated),
            "skipped": len(self.skipped),
            "errors": len(self.errors),
        }


def _iter_files(inbox_dir: Path) -> Iterator[tuple[SourceType, Path, str]]:
    """Yield ``(source_type, file_path, external_id)`` for every ingestible file."""
    for subdir, source_type in _SUBDIR_TO_SOURCE.items():
        base = inbox_dir / subdir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if path.suffix.lower() not in _ALLOWED_EXTS:
                continue
            rel = path.relative_to(base).as_posix()
            yield source_type, path, f"{subdir}/{rel}"


def _extract_title(text: str, fallback: str) -> str:
    """Use the first Markdown H1 if the file starts with one, else the filename stem."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            return stripped[2:].strip() or fallback
        break
    return fallback


def _compose(title: str, body: str) -> str:
    """Mirror documents router behaviour: prepend an H1 title."""
    return f"# {title}\n\n{body}"


async def _resolve_project_id(
    project_repo: ProjectRepository,
    configured_project_id: str | None,
) -> ProjectId | None:
    if configured_project_id:
        return ProjectId(configured_project_id)
    projects = await project_repo.find_all()
    if len(projects) == 1:
        return projects[0].id
    if not projects:
        logger.warning("inbox_scan_skipped: no projects exist in repo")
    else:
        logger.warning(
            "inbox_scan_skipped: multiple projects exist (%d). "
            "Set CH_PROJECT_ID to disambiguate.",
            len(projects),
        )
    return None


async def scan_inbox(
    inbox_dir: Path,
    project_repo: ProjectRepository,
    document_repo: DocumentRepository,
    embedding: EmbeddingProvider,
    configured_project_id: str | None = None,
) -> InboxScanResult:
    """One pass over the inbox directory tree. Idempotent — safe to run on a schedule."""
    result = InboxScanResult()
    if not inbox_dir.is_dir():
        return result

    project_id = await _resolve_project_id(project_repo, configured_project_id)
    if project_id is None:
        return result

    for source_type, path, external_id in _iter_files(inbox_dir):
        try:
            raw_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("inbox_read_failed path=%s err=%s", path, exc)
            result.errors.append((str(path), str(exc)))
            continue

        if not raw_text.strip():
            # Skip empty files — RawContent rejects empty text and we'd just churn.
            result.skipped.append(external_id)
            continue

        title = _extract_title(raw_text, fallback=path.stem)
        composed = _compose(title, raw_text)

        existing = await document_repo.find_by_external_id(
            project_id, source_type, external_id
        )
        if existing is not None and existing.raw_content.text == composed:
            result.skipped.append(external_id)
            continue

        try:
            vector = await embedding.embed(composed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("inbox_embed_failed path=%s err=%s", path, exc)
            result.errors.append((str(path), str(exc)))
            continue

        doc = Document.create(
            project_id=project_id,
            source_type=source_type,
            external_id=external_id,
            raw_content=RawContent(
                text=composed,
                source_url=path.as_uri(),
                author_id=None,
                created_at=datetime.now(timezone.utc),
            ),
        ).with_embedding(vector)

        try:
            await document_repo.save(doc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("inbox_save_failed path=%s err=%s", path, exc)
            result.errors.append((str(path), str(exc)))
            continue

        if existing is None:
            result.ingested.append(external_id)
        else:
            result.updated.append(external_id)

    logger.info("inbox_scan_complete %s", result.as_dict())
    return result
