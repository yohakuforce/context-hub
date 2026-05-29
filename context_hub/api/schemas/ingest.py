"""Schemas for pushing externally-scraped source data into Context-Hub.

Used by the Slack scraping pipeline: koya scrapes Slack via the web UI (no Slack
API token) and pushes the result here, so Context-Hub treats scraped messages
exactly like adapter-ingested ones (source_type=slack).
"""

from __future__ import annotations

from .common import CamelModel


class SlackScrapedMessage(CamelModel):
    """One scraped Slack message. `ts` is the Slack timestamp = stable id."""

    ts: str
    text: str
    user: str | None = None
    user_name: str | None = None
    channel: str | None = None
    thread_ts: str | None = None
    permalink: str | None = None


class SlackIngestRequest(CamelModel):
    messages: list[SlackScrapedMessage]


class SlackIngestResponse(CamelModel):
    ingested: int
    updated: int
    skipped: int
    document_ids: list[str]
