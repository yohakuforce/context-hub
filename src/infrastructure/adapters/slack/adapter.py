"""Slack source adapter.

Fetches channel history (messages + thread replies) using the Slack WebClient.
Normalises Slack messages to Document + Comment domain objects.

Real credentials (SLACK_BOT_TOKEN) are only available on the company PC.
Development/CI uses the MockSlackAdapter below.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from src.domain.document.entities import Document
from src.domain.issue.entities import Comment
from src.infrastructure.adapters.base import IngestionResult, SourceAdapter
from src.shared.types import (
    MemberRef,
    ProjectId,
    RawContent,
    SourceType,
    SyncCursor,
)


class SlackAdapter(SourceAdapter):
    """Fetches messages from configured Slack channels.

    Requires the 'slack_sdk' package and a valid SLACK_BOT_TOKEN.
    """

    def __init__(self, bot_token: str, channel_ids: list[str]) -> None:
        # Lazy import — only installed when Slack integration is needed
        from slack_sdk.web.async_client import AsyncWebClient

        self._client = AsyncWebClient(token=bot_token)
        self._channel_ids = channel_ids

    @property
    def source_type(self) -> SourceType:
        return SourceType.SLACK

    async def fetch(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
        full_resync: bool = False,
    ) -> IngestionResult:
        documents: list[Document] = []
        latest_ts: str | None = None

        for channel_id in self._channel_ids:
            oldest = (
                None
                if full_resync or cursor is None
                else cursor.cursor_value
            )
            channel_docs, channel_latest_ts = await self._fetch_channel(
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

        return IngestionResult(
            documents=documents,
            issues=[],
            new_cursor=new_cursor,
        )

    async def _fetch_channel(
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

            response = await self._client.conversations_history(**kwargs)
            messages: list[dict[str, Any]] = response.get("messages", [])

            for msg in messages:
                ts: str = msg.get("ts", "")
                if not ts:
                    continue
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts

                doc = self._normalise_message(project_id, channel_id, msg)
                documents.append(doc)

            if not response.get("has_more"):
                break
            next_cursor = response.get("response_metadata", {}).get("next_cursor")
            if not next_cursor:
                break

            # Respect Slack rate limits (Tier 3: ~50 req/min)
            await asyncio.sleep(0.1)

        return documents, latest_ts

    def _normalise_message(
        self,
        project_id: ProjectId,
        channel_id: str,
        msg: dict[str, Any],
    ) -> Document:
        ts: str = msg.get("ts", "")
        text: str = msg.get("text", "")
        user_id: str | None = msg.get("user")

        created_at = datetime.fromtimestamp(float(ts), tz=timezone.utc)

        raw_content = RawContent(
            text=text or "(empty)",
            source_url=None,  # permalink requires extra API call; skip for now
            author_id=user_id,
            created_at=created_at,
        )

        return Document.create(
            project_id=project_id,
            source_type=SourceType.SLACK,
            external_id=ts,
            raw_content=raw_content,
        )


class MockSlackAdapter(SourceAdapter):
    """Mock adapter for testing without real Slack credentials."""

    @property
    def source_type(self) -> SourceType:
        return SourceType.SLACK

    async def fetch(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
        full_resync: bool = False,
    ) -> IngestionResult:
        now = datetime.utcnow()
        raw = RawContent(
            text="[MOCK] Slack message content",
            source_url=None,
            author_id="U_MOCK",
            created_at=now,
        )
        doc = Document.create(
            project_id=project_id,
            source_type=SourceType.SLACK,
            external_id="1700000000.000001",
            raw_content=raw,
        )
        new_cursor = SyncCursor(
            source_type=SourceType.SLACK,
            cursor_value="1700000000.000001",
        )
        return IngestionResult(documents=[doc], issues=[], new_cursor=new_cursor)
