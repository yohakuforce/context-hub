"""Connection checks for the admin GUI "Test" buttons.

Two layers:
  1. Readiness — are the required settings present for a source? (pure, offline)
  2. Live ping — a lightweight real call where it's reliable (Slack auth.test,
     Redmine users/current.json). Best-effort, short timeout, never raises.

Backlog and Gmail report readiness only (Gmail also checks the token file exists);
a full live OAuth/Backlog probe is left to a future iteration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from context_hub.config import settings

_TIMEOUT_SECONDS = 6.0
_TESTABLE = ("slack", "backlog", "redmine", "gmail")


@dataclass(frozen=True)
class SourceCheck:
    """Result of checking one source's connection settings."""

    source: str
    ok: bool
    detail: str
    live: bool  # True ⇒ a real network call was made


def required_present(source: str) -> tuple[bool, str]:
    """Return (ok, message) for whether the required settings for *source* are set.

    Pure / offline — used both directly and as the precondition for a live ping.
    """
    if source == "slack":
        return (
            (True, "Token present")
            if settings.slack_bot_token
            else (False, "SLACK_BOT_TOKEN is not set")
        )
    if source == "backlog":
        if settings.backlog_api_key and settings.backlog_space_key:
            return True, "API key and space key present"
        return False, "BACKLOG_API_KEY and BACKLOG_SPACE_KEY are required"
    if source == "redmine":
        if settings.redmine_api_key and settings.redmine_base_url:
            return True, "API key and base URL present"
        return False, "REDMINE_API_KEY and REDMINE_BASE_URL are required"
    if source == "gmail":
        cred = settings.gmail_credentials_file
        if not cred:
            return False, "GMAIL_CREDENTIALS_FILE is not set"
        if not Path(cred).expanduser().exists():
            return False, f"Credentials file not found: {cred}"
        token = settings.gmail_token_file
        if token and Path(token).expanduser().exists():
            return True, "Credentials and cached token present"
        return True, "Credentials present (token created on first live sync)"
    return False, f"Unknown source: {source}"


async def _ping_slack() -> SourceCheck:
    headers = {"Authorization": f"Bearer {settings.slack_bot_token}"}
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.get("https://slack.com/api/auth.test", headers=headers)
    body = resp.json()
    if body.get("ok"):
        team = body.get("team", "?")
        return SourceCheck("slack", True, f"Authenticated to Slack workspace '{team}'", True)
    return SourceCheck("slack", False, f"Slack rejected the token: {body.get('error')}", True)


async def _ping_redmine() -> SourceCheck:
    base = (settings.redmine_base_url or "").rstrip("/")
    headers = {"X-Redmine-API-Key": settings.redmine_api_key or ""}
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.get(f"{base}/users/current.json", headers=headers)
    if resp.status_code == 200:
        return SourceCheck("redmine", True, "Authenticated to Redmine", True)
    return SourceCheck("redmine", False, f"Redmine returned HTTP {resp.status_code}", True)


async def check_source(source: str) -> SourceCheck:
    """Check one source: readiness first, then a best-effort live ping where supported."""
    if source not in _TESTABLE:
        return SourceCheck(source, False, f"Unknown or untestable source: {source}", False)

    ready, msg = required_present(source)
    if not ready:
        return SourceCheck(source, False, msg, False)

    try:
        if source == "slack":
            return await _ping_slack()
        if source == "redmine":
            return await _ping_redmine()
    except httpx.HTTPError as exc:
        return SourceCheck(source, False, f"Network error: {exc}", True)

    # backlog / gmail: readiness only.
    return SourceCheck(source, True, msg + " (readiness only — no live ping)", False)
