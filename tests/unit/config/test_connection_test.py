"""Tests for connection readiness checks (offline / deterministic parts)."""

from __future__ import annotations

import pytest

from context_hub.config import connection_test
from context_hub.config.connection_test import check_source, required_present


@pytest.fixture(autouse=True)
def clear_source_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank out all source credentials on the live settings singleton."""
    s = connection_test.settings
    for attr in (
        "slack_bot_token",
        "backlog_api_key",
        "backlog_space_key",
        "redmine_api_key",
        "redmine_base_url",
        "gmail_credentials_file",
        "gmail_token_file",
    ):
        monkeypatch.setattr(s, attr, None, raising=False)


class TestRequiredPresent:
    def test_slack_missing(self) -> None:
        ok, msg = required_present("slack")
        assert ok is False and "SLACK_BOT_TOKEN" in msg

    def test_backlog_requires_both(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(connection_test.settings, "backlog_api_key", "k")
        assert required_present("backlog")[0] is False  # space key still missing
        monkeypatch.setattr(connection_test.settings, "backlog_space_key", "x.backlog.jp")
        assert required_present("backlog")[0] is True

    def test_redmine_requires_both(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(connection_test.settings, "redmine_api_key", "k")
        monkeypatch.setattr(connection_test.settings, "redmine_base_url", "http://r")
        assert required_present("redmine")[0] is True

    def test_unknown_source(self) -> None:
        assert required_present("github")[0] is False


class TestCheckSource:
    @pytest.mark.asyncio
    async def test_missing_config_returns_not_ok_without_network(self) -> None:
        r = await check_source("slack")
        assert r.ok is False and r.live is False

    @pytest.mark.asyncio
    async def test_untestable_source(self) -> None:
        r = await check_source("nope")
        assert r.ok is False and "untestable" in r.detail.lower()

    @pytest.mark.asyncio
    async def test_backlog_ready_is_readiness_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(connection_test.settings, "backlog_api_key", "k")
        monkeypatch.setattr(connection_test.settings, "backlog_space_key", "x.backlog.jp")
        r = await check_source("backlog")
        assert r.ok is True and r.live is False  # no live ping for backlog
