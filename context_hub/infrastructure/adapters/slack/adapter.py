"""Slack source adapter (live + mock).

Live mode  (INGEST_MODE=live):  uses Slack WebClient with SLACK_BOT_TOKEN.
Mock mode  (INGEST_MODE=mock):  uses fixture JSON bundled at context_hub/_fixtures/slack/.

Switch:  set environment variable INGEST_MODE=live|mock  (default: mock)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from context_hub.domain.document.entities import Document
from context_hub.infrastructure.adapters.base import IngestionResult, SourceAdapter
from context_hub.shared.types import (
    ProjectId,
    RawContent,
    SourceType,
    SyncCursor,
)


_FIXTURE_DIR = (
    Path(__file__).parent.parent.parent.parent / "_fixtures" / "slack"
)


class SlackAdapter(SourceAdapter):
    """Fetches messages from configured Slack channels.

    Args:
        bot_token:   Slack bot OAuth token (SLACK_BOT_TOKEN).
        channel_ids: List of Slack channel IDs to sync.
        ingest_mode: "live" | "mock"
    """

    def __init__(
        self,
        bot_token: str,
        channel_ids: list[str],
        ingest_mode: str = "mock",
    ) -> None:
        self._channel_ids = channel_ids
        self._ingest_mode = ingest_mode

        if ingest_mode == "live":
            # Lazy import — only installed when live Slack integration is needed
            from slack_sdk.web.async_client import AsyncWebClient
            self._live_client = AsyncWebClient(token=bot_token)
        else:
            self._live_client = None

    @property
    def source_type(self) -> SourceType:
        return SourceType.SLACK

    async def fetch(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
        full_resync: bool = False,
    ) -> IngestionResult:
        if self._ingest_mode == "live":
            return await self._fetch_live(project_id, cursor, full_resync)
        # In mock mode, full_resync=True ignores cursor
        effective_cursor = None if full_resync else cursor
        return await self._fetch_mock(project_id, effective_cursor)

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
        documents: list[Document] = []
        latest_ts: str | None = None

        for channel_id in self._channel_ids:
            oldest = (
                None
                if full_resync or cursor is None
                else cursor.cursor_value
            )
            channel_docs, channel_latest_ts = await self._fetch_channel_live(
                project_id, channel_id, oldest
            )
            documents.extend(channel_docs)
            if channel_latest_ts:
                if latest_ts is None or channel_latest_ts > latest_ts:
                    latest_ts = channel_latest_ts

        new_cursor = (
            SyncCursor(source_type=SourceType.SLACK, cursor_value=latest_ts)
            if latest_ts
            else cursor
        )
        return IngestionResult(documents=documents, issues=[], new_cursor=new_cursor)

    async def _fetch_channel_live(
        self,
        project_id: ProjectId,
        channel_id: str,
        oldest: str | None,
    ) -> tuple[list[Document], str | None]:
        documents: list[Document] = []
        latest_ts: str | None = None
        next_cursor: str | None = None

        while True:
            kwargs: dict[str, Any] = {"channel": channel_id, "limit": 200}
            if oldest:
                kwargs["oldest"] = oldest
            if next_cursor:
                kwargs["cursor"] = next_cursor

            response = await self._live_client.conversations_history(**kwargs)
            messages: list[dict[str, Any]] = response.get("messages", [])

            for msg in messages:
                ts: str = msg.get("ts", "")
                if not ts:
                    continue
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
                doc = _normalise_message(project_id, msg)
                documents.append(doc)

            if not response.get("has_more"):
                break
            next_cursor = response.get("response_metadata", {}).get("next_cursor")
            if not next_cursor:
                break

            # Respect Slack rate limits (Tier 3: ~50 req/min)
            await asyncio.sleep(0.1)

        return documents, latest_ts

    # ------------------------------------------------------------------
    # Mock implementation (uses fixture JSON)
    # ------------------------------------------------------------------

    async def _fetch_mock(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
    ) -> IngestionResult:
        fixture_path = _FIXTURE_DIR / "conversations_history.json"
        with fixture_path.open(encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)

        messages: list[dict[str, Any]] = data.get("messages", [])
        documents: list[Document] = []
        latest_ts: str | None = None

        for msg in messages:
            ts: str = msg.get("ts", "")
            if cursor and cursor.cursor_value and ts <= cursor.cursor_value:
                continue  # skip already-seen messages
            if not ts:
                continue
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
            doc = _normalise_message(project_id, msg)
            documents.append(doc)

        new_cursor = (
            SyncCursor(source_type=SourceType.SLACK, cursor_value=latest_ts)
            if latest_ts
            else cursor
        )
        return IngestionResult(documents=documents, issues=[], new_cursor=new_cursor)


def _normalise_message(
    project_id: ProjectId,
    msg: dict[str, Any],
) -> Document:
    ts: str = msg.get("ts", "")
    text: str = msg.get("text", "")
    user_id: str | None = msg.get("user")

    created_at = datetime.fromtimestamp(float(ts), tz=timezone.utc)

    raw_content = RawContent(
        text=text or "(empty)",
        source_url=None,
        author_id=user_id,
        created_at=created_at,
    )
    return Document.create(
        project_id=project_id,
        source_type=SourceType.SLACK,
        external_id=ts,
        raw_content=raw_content,
    )
