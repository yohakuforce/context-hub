"""Backlog source adapter (live + mock).

Live mode  (INGEST_MODE=live):  uses BacklogClient with real API key.
Mock mode  (INGEST_MODE=mock):  uses fixture JSON bundled at context_hub/_fixtures/backlog/.

Switch:  set environment variable INGEST_MODE=live|mock  (default: mock)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_hub.domain.document.entities import Document
from context_hub.domain.issue.entities import Issue
from context_hub.infrastructure.adapters.backlog.client import BacklogClient
from context_hub.infrastructure.adapters.backlog.normalizer import (
    normalise_issue,
    normalise_wiki,
    normalise_comment,
)
from context_hub.infrastructure.adapters.base import IngestionResult, SourceAdapter
from context_hub.infrastructure.adapters.mock_http_client import MockHttpClient
from context_hub.shared.types import ProjectId, SourceType, SyncCursor


_FIXTURE_DIR = (
    Path(__file__).parent.parent.parent.parent / "_fixtures" / "backlog"
)


class BacklogAdapter(SourceAdapter):
    """Fetches issues + wikis from a Backlog project.

    Args:
        space_key:           Backlog space subdomain.
        api_key:             Backlog API key (only required in live mode).
        backlog_project_key: Project key string (e.g. "PROJ").
        include_wiki:        Whether to also sync wiki pages.
        ingest_mode:         "live" | "mock"
    """

    def __init__(
        self,
        space_key: str,
        api_key: str,
        backlog_project_key: str,
        include_wiki: bool = True,
        ingest_mode: str = "mock",
    ) -> None:
        self._space_key = space_key
        self._backlog_project_key = backlog_project_key
        self._include_wiki = include_wiki
        self._ingest_mode = ingest_mode

        if ingest_mode == "live":
            self._live_client: BacklogClient | None = BacklogClient(
                space_key=space_key, api_key=api_key
            )
        else:
            self._live_client = None

    @property
    def source_type(self) -> SourceType:
        return SourceType.BACKLOG

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

        updated_since: str | None = None
        if not full_resync and cursor and cursor.cursor_value:
            updated_since = cursor.cursor_value

        issues: list[Issue] = []
        documents: list[Document] = []
        latest_updated: str | None = None

        # Paginate issues
        offset = 0
        while True:
            raw_issues = await client.get_issues(
                project_id=self._backlog_project_key,
                updated_since=updated_since,
                offset=offset,
            )
            if not raw_issues:
                break

            for raw in raw_issues:
                issue = normalise_issue(raw, project_id)
                # Fetch comments
                comments_raw = await client.get_issue_comments(raw["id"])
                comments = [normalise_comment(c) for c in comments_raw]
                if comments:
                    issue = issue.with_comments(comments)
                issues.append(issue)

                updated_str: str = raw.get("updated", "")
                if updated_str and (
                    latest_updated is None or updated_str > latest_updated
                ):
                    latest_updated = updated_str

            if len(raw_issues) < 100:
                break
            offset += 100

        if self._include_wiki:
            wiki_docs = await self._fetch_wikis_live(project_id, client)
            documents.extend(wiki_docs)

        new_cursor = (
            SyncCursor(
                source_type=SourceType.BACKLOG,
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
        client: BacklogClient,
    ) -> list[Document]:
        docs: list[Document] = []
        wiki_list = await client.get_wikis(self._backlog_project_key)
        for stub in wiki_list:
            wiki_full = await client.get_wiki(stub["id"])
            doc = normalise_wiki(wiki_full, project_id, self._space_key)
            docs.append(doc)
        return docs

    # ------------------------------------------------------------------
    # Mock implementation (uses fixture JSON)
    # ------------------------------------------------------------------

    async def _fetch_mock(self, project_id: ProjectId) -> IngestionResult:
        import json

        issues_path = _FIXTURE_DIR / "issues.json"
        comments_path = _FIXTURE_DIR / "issue_comments.json"
        wikis_path = _FIXTURE_DIR / "wikis.json"

        raw_issues: list[dict[str, Any]] = _load_json(issues_path)
        raw_comments: list[dict[str, Any]] = _load_json(comments_path)
        raw_wikis: list[dict[str, Any]] = _load_json(wikis_path)

        issues: list[Issue] = []
        for raw in raw_issues:
            issue = normalise_issue(raw, project_id)
            comments = [normalise_comment(c) for c in raw_comments]
            if comments:
                issue = issue.with_comments(comments)
            issues.append(issue)

        documents: list[Document] = []
        if self._include_wiki:
            for raw in raw_wikis:
                doc = normalise_wiki(raw, project_id, self._space_key)
                documents.append(doc)

        latest_updated = max(
            (r.get("updated", "") for r in raw_issues), default=""
        )
        new_cursor = SyncCursor(
            source_type=SourceType.BACKLOG,
            cursor_value=latest_updated,
        )
        return IngestionResult(
            documents=documents,
            issues=issues,
            new_cursor=new_cursor,
        )


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return __import__("json").load(fh)
