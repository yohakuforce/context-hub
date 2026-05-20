"""Gmail source adapter (live + mock).

Live mode  (INGEST_MODE=live):
    OAuth2 via google-api-python-client. Requires:
      - GMAIL_CREDENTIALS_FILE  → path to credentials.json from Google Cloud Console
      - GMAIL_TOKEN_FILE        → path where the refresh-token cache is stored
                                  (created automatically on first browser consent)
      - GMAIL_QUERY             → Gmail search query (default: "label:context-hub")
    On first run, opens a browser for user consent. Subsequent runs reuse the
    refresh token cached in GMAIL_TOKEN_FILE.

    Install the dependency with:
        pip install 'yohakuforce-context-hub[gmail]'

Mock mode  (INGEST_MODE=mock):
    Uses fixture JSON bundled at context_hub/_fixtures/gmail/messages.json.
    No auth required.

Cursor strategy
---------------
SyncCursor.cursor_value stores the ``internalDate`` (epoch milliseconds) of the
newest message seen. Next sync appends ``after:<seconds>`` to the configured
query so Gmail only returns newer messages.

Filter rationale
----------------
The default query ``label:context-hub`` is explicit opt-in — users label
relevant emails in Gmail, and only those are ingested. This keeps private mail
out of the Context-Hub store. Override via the GMAIL_QUERY env var or per-call.
"""

from __future__ import annotations

import json
import re
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
    Path(__file__).parent.parent.parent.parent / "_fixtures" / "gmail"
)

# Gmail OAuth scope — read-only access is sufficient for ingestion.
_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailAdapter(SourceAdapter):
    """Fetches messages from Gmail matching a configured query.

    Args:
        credentials_file: Path to Google OAuth client credentials.json
                          (downloaded from Google Cloud Console).
        token_file:       Path where the cached refresh token is stored.
        query:            Gmail search query string.
                          Defaults to "label:context-hub" so only explicitly
                          labelled mail is ingested.
        ingest_mode:      "live" | "mock"
    """

    def __init__(
        self,
        credentials_file: str | None = None,
        token_file: str | None = None,
        query: str = "label:context-hub",
        ingest_mode: str = "mock",
    ) -> None:
        self._credentials_file = credentials_file
        self._token_file = token_file
        self._query = query
        self._ingest_mode = ingest_mode

    @property
    def source_type(self) -> SourceType:
        return SourceType.EMAIL

    async def fetch(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
        full_resync: bool = False,
    ) -> IngestionResult:
        if self._ingest_mode == "live":
            return await self._fetch_live(project_id, cursor, full_resync)
        effective_cursor = None if full_resync else cursor
        return await self._fetch_mock(project_id, effective_cursor)

    # ------------------------------------------------------------------
    # Live implementation (Google API)
    # ------------------------------------------------------------------

    async def _fetch_live(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
        full_resync: bool,
    ) -> IngestionResult:
        # Lazy import — only required when extras are installed.
        from googleapiclient.discovery import build  # type: ignore[import-not-found]

        creds = self._load_credentials()
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        effective_cursor = None if full_resync else cursor
        query = self._build_query(effective_cursor)

        documents: list[Document] = []
        latest_internal_date: int | None = None
        page_token: str | None = None

        while True:
            req_kwargs: dict[str, Any] = {"userId": "me", "q": query, "maxResults": 100}
            if page_token:
                req_kwargs["pageToken"] = page_token
            response = service.users().messages().list(**req_kwargs).execute()
            messages = response.get("messages", [])

            for msg_ref in messages:
                full = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_ref["id"], format="full")
                    .execute()
                )
                normalised = _normalise_live_message(project_id, full)
                if normalised is None:
                    continue
                doc, internal_date = normalised
                documents.append(doc)
                if latest_internal_date is None or internal_date > latest_internal_date:
                    latest_internal_date = internal_date

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        new_cursor = (
            SyncCursor(source_type=SourceType.EMAIL, cursor_value=str(latest_internal_date))
            if latest_internal_date is not None
            else cursor
        )
        return IngestionResult(documents=documents, issues=[], new_cursor=new_cursor)

    def _load_credentials(self) -> Any:
        """Load cached OAuth credentials, refreshing or running the consent flow as needed."""
        # Lazy imports — only required when [gmail] extra is installed.
        from google.auth.transport.requests import Request  # type: ignore[import-not-found]
        from google.oauth2.credentials import Credentials  # type: ignore[import-not-found]
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-not-found]

        if not self._credentials_file:
            raise RuntimeError(
                "GMAIL_CREDENTIALS_FILE is not set — cannot run Gmail live ingest."
            )
        token_path = Path(self._token_file) if self._token_file else None
        creds = None
        if token_path and token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), _GMAIL_SCOPES)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                self._credentials_file, _GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        if token_path:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def _build_query(self, cursor: SyncCursor | None) -> str:
        base = self._query.strip() or "label:context-hub"
        if cursor and cursor.cursor_value:
            # Gmail's after: takes seconds since epoch
            try:
                after_seconds = int(cursor.cursor_value) // 1000
                return f"{base} after:{after_seconds}"
            except ValueError:
                return base
        return base

    # ------------------------------------------------------------------
    # Mock implementation (fixture JSON)
    # ------------------------------------------------------------------

    async def _fetch_mock(
        self,
        project_id: ProjectId,
        cursor: SyncCursor | None,
    ) -> IngestionResult:
        fixture_path = _FIXTURE_DIR / "messages.json"
        with fixture_path.open(encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)

        documents: list[Document] = []
        latest_internal_date: int | None = None
        cursor_value = int(cursor.cursor_value) if cursor and cursor.cursor_value else None

        for msg in data.get("messages", []):
            internal_date = int(msg.get("internalDate", "0"))
            if cursor_value is not None and internal_date <= cursor_value:
                continue
            documents.append(_normalise_mock_message(project_id, msg))
            if latest_internal_date is None or internal_date > latest_internal_date:
                latest_internal_date = internal_date

        new_cursor = (
            SyncCursor(source_type=SourceType.EMAIL, cursor_value=str(latest_internal_date))
            if latest_internal_date is not None
            else cursor
        )
        return IngestionResult(documents=documents, issues=[], new_cursor=new_cursor)


# ----------------------------------------------------------------------
# Normalisation helpers
# ----------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_WHITESPACE_RE = re.compile(r"\n\s*\n\s*\n+")


def _strip_html(html: str) -> str:
    """Very small HTML→text pass.

    We deliberately avoid a full HTML parser dependency. Email bodies are
    typically short and well-formed; for anything richer (newsletters, marketing)
    users are better served by filtering those out via the Gmail query.
    """
    text = html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = text.replace("</p>", "\n").replace("</div>", "\n")
    text = _HTML_TAG_RE.sub("", text)
    text = _HTML_WHITESPACE_RE.sub("\n\n", text)
    return text.strip()


def _compose_body(subject: str, sender: str | None, body: str) -> str:
    header_line = f"From: {sender}" if sender else ""
    parts = [f"# {subject}" if subject else "# (no subject)"]
    if header_line:
        parts.append(header_line)
    parts.append("")
    parts.append(body.strip() or "(empty body)")
    return "\n".join(parts)


def _normalise_mock_message(project_id: ProjectId, msg: dict[str, Any]) -> Document:
    headers = msg.get("headers", {})
    subject = headers.get("Subject", "")
    sender = headers.get("From")
    internal_date_ms = int(msg.get("internalDate", "0"))
    created_at = datetime.fromtimestamp(internal_date_ms / 1000.0, tz=timezone.utc)

    if "body_text" in msg:
        body = msg["body_text"]
    elif "body_html" in msg:
        body = _strip_html(msg["body_html"])
    else:
        body = ""

    composed = _compose_body(subject, sender, body)
    raw_content = RawContent(
        text=composed,
        source_url=f"https://mail.google.com/mail/u/0/#inbox/{msg['id']}",
        author_id=sender,
        created_at=created_at,
    )
    return Document.create(
        project_id=project_id,
        source_type=SourceType.EMAIL,
        external_id=msg["id"],
        raw_content=raw_content,
    )


def _normalise_live_message(
    project_id: ProjectId,
    full: dict[str, Any],
) -> tuple[Document, int] | None:
    """Convert a Gmail ``messages.get`` payload to a Document.

    Returns None when the message has no extractable body.
    """
    msg_id = full.get("id")
    if not msg_id:
        return None
    internal_date = int(full.get("internalDate", "0"))
    headers_list = full.get("payload", {}).get("headers", [])
    headers = {h.get("name", ""): h.get("value", "") for h in headers_list}
    subject = headers.get("Subject", "")
    sender = headers.get("From")

    body = _extract_body(full.get("payload", {}))
    if not body:
        return None

    composed = _compose_body(subject, sender, body)
    created_at = datetime.fromtimestamp(internal_date / 1000.0, tz=timezone.utc)
    raw_content = RawContent(
        text=composed,
        source_url=f"https://mail.google.com/mail/u/0/#inbox/{msg_id}",
        author_id=sender,
        created_at=created_at,
    )
    doc = Document.create(
        project_id=project_id,
        source_type=SourceType.EMAIL,
        external_id=msg_id,
        raw_content=raw_content,
    )
    return doc, internal_date


def _extract_body(payload: dict[str, Any]) -> str:
    """Walk the MIME tree, preferring text/plain, falling back to text/html."""
    import base64

    def decode(data: str) -> str:
        # Gmail uses URL-safe base64 without padding
        pad = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + pad).decode("utf-8", errors="replace")

    def walk(node: dict[str, Any], prefer_plain: bool) -> str | None:
        mime = node.get("mimeType", "")
        body = node.get("body", {})
        data = body.get("data")
        if mime.startswith("text/") and data:
            text = decode(data)
            if mime == "text/plain" and prefer_plain:
                return text
            if mime == "text/html" and not prefer_plain:
                return _strip_html(text)
            # Mismatched mime — return None to keep walking
        for part in node.get("parts", []) or []:
            found = walk(part, prefer_plain)
            if found:
                return found
        return None

    plain = walk(payload, prefer_plain=True)
    if plain:
        return plain
    html = walk(payload, prefer_plain=False)
    return html or ""
