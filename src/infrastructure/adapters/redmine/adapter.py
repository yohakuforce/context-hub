"""Redmine source adapter (live + mock).

Live mode  (INGEST_MODE=live):  uses RedmineClient with real API key.
Mock mode  (INGEST_MODE=mock):  uses fixture JSON files from tests/fixtures/redmine/.

Switch:  set environment variable INGEST_MODE=live|mock  (default: mock)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.domain.document.entities import Document
from src.domain.issue.entities import Issue
from src.infrastructure.adapters.redmine.client import RedmineClient
from src.infrastructure.adapters.redmine.normalizer import (
    normalise_issue,
    normalise_wiki,
)
from src.infrastructure.adapters.base import IngestionResult, SourceAdapter
from src.shared.types import ProjectId, SourceType, SyncCursor


_FIXTURE_DIR = (
    Path(__file__).parent.parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "redmine"
)


class RedmineAdapter(SourceAdapter):
    """Fetches issues + wiki pages from a Redmine project.

    Args:
        base_url:                    Redmine instance URL.
        api_key:                     X-Redmine-API-Key (only in live mode).
        redmine_project_identifier:  Project identifier string.
        include_wiki:                Whether to also sync wiki pages.
        ingest_mode:                 "live" | "mock"
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        redmine_project_identifier: str,
        include_wiki: bool = True,
        ingest_mode: str = "mock",
    ) -> None:
        self._base_url = base_url
        self._project_identifier = redmine_project_identifier
        self._include_wiki = include_wiki
        self._ingest_mode = ingest_mode

        if ingest_mode == "live":
            self._live_client: RedmineClient | None = RedmineClient(
                base_url=base_url, api_key=api_key
            )
        else:
            self._live_client = None

    @property
    def source_type(self) -> SourceType:
        return SourceType.REDMINE

    async def fetch(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
        full_resync: bool = False,
    ) -> IngestionResult:
        if self._ingest_mode == "live":
            return await self._fetch_live(project_id, cursor, full_resync)
        return await self._fetch_mock(project_id)

    # ------------------------------------------------------------------
    # Live implementation
    # ------------------------------------------------------------------

    async def _fetch_live(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
        full_resync: bool,
    ) -> IngestionResult:
        assert self._live_client is not None
        client = self._live_client

        updated_on: str | None = None
        if not full_resync and cursor and cursor.cursor_value:
            updated_on = cursor.cursor_value

        issues: list[Issue] = []
        documents: list[Document] = []
        latest_updated: str | None = None

        offset = 0
        while True:
            response = await client.get_issues(
                project_identifier=self._project_identifier,
                updated_on=updated_on,
                offset=offset,
            )
            raw_issues: list[dict[str, Any]] = response.get("issues", [])
            total_count: int = response.get("total_count", 0)

            for raw in raw_issues:
                issue = normalise_issue(raw, project_id)
                issues.append(issue)

                updated_str: str = raw.get("updated_on", "")
                if updated_str and (
                    latest_updated is None or updated_str > latest_updated
                ):
                    latest_updated = updated_str

            offset += len(raw_issues)
            if offset >= total_count or not raw_issues:
                break

        if self._include_wiki:
            wiki_docs = await self._fetch_wikis_live(project_id, client)
            documents.extend(wiki_docs)

        new_cursor = (
            SyncCursor(
                source_type=SourceType.REDMINE,
                cursor_value=latest_updated,
            )
            if latest_updated
            else cursor
        )
        return IngestionResult(
            documents=documents,
            issues=issues,
            new_cursor=new_cursor,
        )

    async def _fetch_wikis_live(
        self,
        project_id: ProjectId,
        client: RedmineClient,
    ) -> list[Document]:
        docs: list[Document] = []
        pages = await client.get_wiki_index(self._project_identifier)
        for page in pages:
            title = page.get("title", "")
            if not title:
                continue
            wiki_data = await client.get_wiki_page(self._project_identifier, title)
            doc = normalise_wiki(
                wiki_data,
                project_id,
                self._base_url,
                self._project_identifier,
            )
            docs.append(doc)
        return docs

    # ------------------------------------------------------------------
    # Mock implementation (uses fixture JSON)
    # ------------------------------------------------------------------

    async def _fetch_mock(self, project_id: ProjectId) -> IngestionResult:
        issues_path = _FIXTURE_DIR / "issues.json"
        wiki_index_path = _FIXTURE_DIR / "wiki_index.json"
        wiki_arch_path = _FIXTURE_DIR / "wiki_page_architecture.json"

        response_data: dict[str, Any] = _load_json(issues_path)
        raw_issues: list[dict[str, Any]] = response_data.get("issues", [])

        issues: list[Issue] = []
        latest_updated: str | None = None
        for raw in raw_issues:
            issue = normalise_issue(raw, project_id)
            issues.append(issue)
            updated_str: str = raw.get("updated_on", "")
            if updated_str and (
                latest_updated is None or updated_str > latest_updated
            ):
                latest_updated = updated_str

        documents: list[Document] = []
        if self._include_wiki:
            wiki_index: dict[str, Any] = _load_json(wiki_index_path)
            for page_stub in wiki_index.get("wiki_pages", []):
                title = page_stub.get("title", "")
                wiki_file = _FIXTURE_DIR / f"wiki_page_{title.lower()}.json"
                if wiki_file.exists():
                    wiki_data_wrapper: dict[str, Any] = _load_json(wiki_file)
                    wiki_data = wiki_data_wrapper.get("wiki_page", wiki_data_wrapper)
                else:
                    # Fallback: synthesise minimal wiki data
                    wiki_data = {
                        "title": title,
                        "text": f"[Mock wiki page: {title}]",
                        "created_on": "2026-04-01T09:00:00Z",
                        "updated_on": "2026-05-01T09:00:00Z",
                    }
                doc = normalise_wiki(
                    wiki_data,
                    project_id,
                    self._base_url,
                    self._project_identifier,
                )
                documents.append(doc)

        new_cursor = SyncCursor(
            source_type=SourceType.REDMINE,
            cursor_value=latest_updated or "",
        )
        return IngestionResult(
            documents=documents,
            issues=issues,
            new_cursor=new_cursor,
        )


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return __import__("json").load(fh)
