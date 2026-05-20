"""Integration tests for the Gmail adapter (mock mode).

The live OAuth path is exercised indirectly — these tests cover the mock
fixture path plus the helper logic that the live path also relies on
(HTML stripping, MIME body extraction, query building, cursor semantics).
"""

from __future__ import annotations

import base64

import pytest

from context_hub.infrastructure.adapters.gmail.adapter import (
    GmailAdapter,
    _extract_body,
    _normalise_live_message,
    _strip_html,
)
from context_hub.shared.types import ProjectId, SourceType, SyncCursor


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


class TestGmailMockFetch:
    @pytest.mark.asyncio
    async def test_fetch_returns_documents_from_fixture(self):
        adapter = GmailAdapter(ingest_mode="mock")
        result = await adapter.fetch(ProjectId("proj-001"), cursor=None)

        assert len(result.documents) == 3
        assert all(d.source_type == SourceType.EMAIL for d in result.documents)
        # external_id = Gmail message ID
        external_ids = sorted(d.external_id for d in result.documents)
        assert external_ids == ["m-001", "m-002", "m-003"]

    @pytest.mark.asyncio
    async def test_subject_is_used_as_h1_title(self):
        adapter = GmailAdapter(ingest_mode="mock")
        result = await adapter.fetch(ProjectId("proj-001"), cursor=None)

        m001 = next(d for d in result.documents if d.external_id == "m-001")
        assert m001.raw_content.text.startswith("# Project kickoff — Phase 1")

    @pytest.mark.asyncio
    async def test_from_header_is_captured_as_author(self):
        adapter = GmailAdapter(ingest_mode="mock")
        result = await adapter.fetch(ProjectId("proj-001"), cursor=None)

        m001 = next(d for d in result.documents if d.external_id == "m-001")
        assert m001.raw_content.author_id == "client@example.com"
        assert "From: client@example.com" in m001.raw_content.text

    @pytest.mark.asyncio
    async def test_html_body_is_stripped_to_text(self):
        adapter = GmailAdapter(ingest_mode="mock")
        result = await adapter.fetch(ProjectId("proj-001"), cursor=None)

        m003 = next(d for d in result.documents if d.external_id == "m-003")
        assert "<p>" not in m003.raw_content.text
        assert "<html>" not in m003.raw_content.text
        assert "Please find the quote attached" in m003.raw_content.text

    @pytest.mark.asyncio
    async def test_cursor_filters_older_messages(self):
        adapter = GmailAdapter(ingest_mode="mock")
        # Fixture internalDates: 1700100000000, 1700200000000, 1700300000000.
        cursor = SyncCursor(source_type=SourceType.EMAIL, cursor_value="1700200000000")
        result = await adapter.fetch(ProjectId("proj-001"), cursor=cursor)

        assert {d.external_id for d in result.documents} == {"m-003"}

    @pytest.mark.asyncio
    async def test_cursor_advances_to_newest_internal_date(self):
        adapter = GmailAdapter(ingest_mode="mock")
        result = await adapter.fetch(ProjectId("proj-001"), cursor=None)

        assert result.new_cursor is not None
        assert result.new_cursor.source_type == SourceType.EMAIL
        assert result.new_cursor.cursor_value == "1700300000000"

    @pytest.mark.asyncio
    async def test_full_resync_ignores_cursor(self):
        adapter = GmailAdapter(ingest_mode="mock")
        cursor = SyncCursor(source_type=SourceType.EMAIL, cursor_value="9999999999999")
        result = await adapter.fetch(
            ProjectId("proj-001"), cursor=cursor, full_resync=True
        )

        assert len(result.documents) == 3


class TestGmailQueryBuilding:
    def test_default_query_is_label_based(self):
        adapter = GmailAdapter(ingest_mode="mock")
        assert adapter._build_query(None) == "label:context-hub"

    def test_query_includes_after_when_cursor_present(self):
        adapter = GmailAdapter(ingest_mode="mock", query="label:work")
        cursor = SyncCursor(
            source_type=SourceType.EMAIL, cursor_value="1700100000000"
        )
        # internalDate is ms → after: takes seconds
        assert adapter._build_query(cursor) == "label:work after:1700100000"

    def test_query_handles_malformed_cursor(self):
        adapter = GmailAdapter(ingest_mode="mock", query="label:work")
        cursor = SyncCursor(source_type=SourceType.EMAIL, cursor_value="not-a-number")
        assert adapter._build_query(cursor) == "label:work"

    def test_empty_query_falls_back_to_default(self):
        adapter = GmailAdapter(ingest_mode="mock", query="   ")
        assert adapter._build_query(None) == "label:context-hub"


class TestHtmlStripping:
    def test_paragraphs_become_newlines(self):
        out = _strip_html("<p>line1</p><p>line2</p>")
        assert "line1" in out
        assert "line2" in out
        assert "<p>" not in out

    def test_br_becomes_newline(self):
        out = _strip_html("a<br>b<br/>c")
        assert out.count("\n") >= 2

    def test_collapses_excessive_blank_lines(self):
        out = _strip_html("a</p>\n\n\n\n\nb")
        assert "\n\n\n" not in out


class TestLiveMessageNormalisation:
    """The live path is unreachable without real Google API, but the
    normalisation helpers it relies on must be covered."""

    def test_extract_body_prefers_text_plain(self):
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("plain content")}},
                {"mimeType": "text/html", "body": {"data": _b64("<p>html content</p>")}},
            ],
        }
        assert _extract_body(payload) == "plain content"

    def test_extract_body_falls_back_to_html(self):
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/html", "body": {"data": _b64("<p>html only</p>")}},
            ],
        }
        assert "html only" in _extract_body(payload)
        assert "<p>" not in _extract_body(payload)

    def test_extract_body_handles_nested_parts(self):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": _b64("nested plain")}},
                    ],
                },
            ],
        }
        assert _extract_body(payload) == "nested plain"

    def test_normalise_live_returns_none_when_no_body(self):
        full = {
            "id": "m-xyz",
            "internalDate": "1700400000000",
            "payload": {"headers": [{"name": "Subject", "value": "x"}], "parts": []},
        }
        assert _normalise_live_message(ProjectId("p"), full) is None

    def test_normalise_live_builds_document(self):
        full = {
            "id": "m-live-1",
            "internalDate": "1700400000000",
            "payload": {
                "mimeType": "text/plain",
                "body": {"data": _b64("live body content")},
                "headers": [
                    {"name": "Subject", "value": "Live Subject"},
                    {"name": "From", "value": "live@example.com"},
                ],
            },
        }
        out = _normalise_live_message(ProjectId("p"), full)
        assert out is not None
        doc, internal_date = out
        assert doc.external_id == "m-live-1"
        assert doc.source_type == SourceType.EMAIL
        assert "live body content" in doc.raw_content.text
        assert doc.raw_content.text.startswith("# Live Subject")
        assert internal_date == 1700400000000
