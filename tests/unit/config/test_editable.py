"""Tests for the editable-config registry (admin GUI backend logic).

Covers secret masking, reading current .env values, and writing updates
(set / clear / skip / reject) plus restart-required reporting.
"""

from __future__ import annotations

from pathlib import Path

from context_hub.config.editable import (
    FIELDS,
    mask_secret,
    read_config,
    write_config,
)


class TestMaskSecret:
    def test_empty(self) -> None:
        assert mask_secret("") == ""

    def test_short_value_fully_masked(self) -> None:
        assert mask_secret("abc") == "••••"

    def test_long_value_reveals_last_four(self) -> None:
        assert mask_secret("xoxb-secret-1234") == "••••1234"


class TestReadConfig:
    def test_unset_fields_are_not_configured(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("", encoding="utf-8")
        views = {v.env: v for v in read_config(env)}
        assert views["SLACK_BOT_TOKEN"].configured is False
        assert views["SLACK_BOT_TOKEN"].value == ""

    def test_secret_is_masked_non_secret_is_raw(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "SLACK_BOT_TOKEN=xoxb-aaaa-bbbb-9999\nGMAIL_QUERY=label:foo\n",
            encoding="utf-8",
        )
        views = {v.env: v for v in read_config(env)}
        assert views["SLACK_BOT_TOKEN"].configured is True
        assert views["SLACK_BOT_TOKEN"].value == "••••9999"  # masked
        assert views["GMAIL_QUERY"].value == "label:foo"  # raw (not secret)

    def test_missing_env_file_returns_all_unconfigured(self, tmp_path: Path) -> None:
        views = read_config(tmp_path / "does-not-exist.env")
        assert len(views) == len(FIELDS)
        assert all(v.configured is False for v in views)


class TestWriteConfig:
    def test_set_new_value(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        result = write_config({"SLACK_BOT_TOKEN": "xoxb-zzzz-1111"}, env)
        assert "SLACK_BOT_TOKEN" in result.changed
        views = {v.env: v for v in read_config(env)}
        assert views["SLACK_BOT_TOKEN"].configured is True
        assert views["SLACK_BOT_TOKEN"].value == "••••1111"

    def test_empty_value_clears_key(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("REDMINE_BASE_URL=http://old\n", encoding="utf-8")
        result = write_config({"REDMINE_BASE_URL": ""}, env)
        assert "REDMINE_BASE_URL" in result.cleared
        views = {v.env: v for v in read_config(env)}
        assert views["REDMINE_BASE_URL"].configured is False

    def test_none_value_is_skipped(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("GMAIL_QUERY=label:keep\n", encoding="utf-8")
        result = write_config({"GMAIL_QUERY": None}, env)
        assert result.changed == [] and result.cleared == []
        views = {v.env: v for v in read_config(env)}
        assert views["GMAIL_QUERY"].value == "label:keep"

    def test_unknown_key_is_rejected_not_written(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("", encoding="utf-8")
        result = write_config({"TOTALLY_UNKNOWN": "x"}, env)
        assert result.rejected == ["TOTALLY_UNKNOWN"]
        assert "TOTALLY_UNKNOWN" not in env.read_text(encoding="utf-8")

    def test_restart_required_is_reported(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        result = write_config(
            {"DATABASE_URL": "sqlite+aiosqlite:///./x.db", "GMAIL_QUERY": "label:y"},
            env,
        )
        # DATABASE_URL needs a restart; GMAIL_QUERY does not.
        assert "DATABASE_URL" in result.restart_required
        assert "GMAIL_QUERY" not in result.restart_required

    def test_creates_env_file_when_missing(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        assert not env.exists()
        write_config({"GMAIL_QUERY": "label:new"}, env)
        assert env.exists()
        assert "GMAIL_QUERY" in env.read_text(encoding="utf-8")
