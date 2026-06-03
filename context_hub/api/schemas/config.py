"""Schemas for the admin configuration endpoints (GET/PUT /api/v1/config)."""

from __future__ import annotations

from .common import CamelModel


class ConfigFieldView(CamelModel):
    """One editable setting with its current (masked-if-secret) value + guidance."""

    env: str
    label: str
    group: str
    secret: bool
    kind: str
    options: list[str]
    help: str
    restart_required: bool
    tag: str
    why: str
    steps: list[str]
    how_to_set: str
    configured: bool
    value: str


class ConfigResponse(CamelModel):
    """All editable settings, in display order."""

    fields: list[ConfigFieldView]


class ConfigUpdateRequest(CamelModel):
    """A batch of ``.env`` updates.

    Each entry: value=string sets it, value="" clears it, value=null skips it.
    Keys are the UPPER_SNAKE_CASE env names (e.g. ``SLACK_BOT_TOKEN``).
    """

    updates: dict[str, str | None]


class ConfigUpdateResult(CamelModel):
    """Outcome of a config write."""

    changed: list[str]
    cleared: list[str]
    restart_required: list[str]
    rejected: list[str]
    reloaded: bool


class SourceCheckView(CamelModel):
    """Result of a connection test for one source."""

    source: str
    ok: bool
    detail: str
    live: bool
