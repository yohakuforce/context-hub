"""Integration tests for `context-hub ingest inbox` CLI command.

Uses typer.testing.CliRunner to invoke the CLI with a temporary SQLite DB
and a temporary inbox directory. Patches CH_INBOX_DIR via env vars.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from context_hub.cli.main import app as cli_app

runner = CliRunner()


@pytest.fixture
def tmp_sqlite_db(tmp_path: Path) -> Path:
    """Bootstrap a minimal SQLite DB with a single project row."""
    import sqlite3

    db_path = tmp_path / "context_hub.db"
    schema_dir = Path("context_hub/_sqlite_schema")
    schema_files = sorted(schema_dir.glob("*.sql"))
    assert schema_files, "expected SQLite schema files to seed test DB"

    import sqlite_vec  # type: ignore[import-not-found]

    with sqlite3.connect(db_path) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        for sql_file in schema_files:
            conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.execute(
            """INSERT INTO projects (id, name, external_project_id, sources,
                                     created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "cli-proj-001",
                "CLI Inbox Project",
                "PROJ",
                "[]",
                "2026-05-20T00:00:00",
                "2026-05-20T00:00:00",
            ),
        )
        conn.commit()
    return db_path


@pytest.fixture
def inbox_dir(tmp_path: Path) -> Path:
    root = tmp_path / "inbox"
    (root / "meeting").mkdir(parents=True)
    (root / "file").mkdir(parents=True)
    (root / "email").mkdir(parents=True)
    return root


@pytest.fixture
def cli_env(tmp_sqlite_db: Path, inbox_dir: Path, monkeypatch):
    """Wire env vars so the CLI uses the temp SQLite DB + temp inbox."""
    monkeypatch.setenv("CH_PROFILE", "quickstart")
    monkeypatch.setenv("CH_SQLITE_DB", str(tmp_sqlite_db))
    monkeypatch.setenv(
        "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_sqlite_db}"
    )
    monkeypatch.setenv("CH_INBOX_DIR", str(inbox_dir))
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    # Rebuild the legacy-settings singleton so it picks up the freshly-set env vars.
    # Quirk: `context_hub.config` re-exports the Settings *instance* under the same
    # name as the submodule, so we have to fetch the actual module from sys.modules.
    import sys
    from context_hub.config.settings import Settings
    original_singleton = sys.modules["context_hub.config.settings"].settings  # type: ignore[attr-defined]
    new_settings = Settings()
    sys.modules["context_hub.config.settings"].settings = new_settings  # type: ignore[attr-defined]
    sys.modules["context_hub.config"].settings = new_settings  # type: ignore[attr-defined]
    try:
        yield
    finally:
        # Restore so other tests see the production singleton again.
        sys.modules["context_hub.config.settings"].settings = original_singleton  # type: ignore[attr-defined]
        sys.modules["context_hub.config"].settings = original_singleton  # type: ignore[attr-defined]


class TestCliIngestInbox:
    def test_inbox_ingest_picks_up_new_file(self, inbox_dir, cli_env):
        (inbox_dir / "meeting" / "kickoff.md").write_text(
            "# Kickoff\n\n2026-05-20 project kickoff notes.", encoding="utf-8"
        )
        result = runner.invoke(cli_app, ["ingest", "inbox"])
        assert result.exit_code == 0, result.output
        assert "ingested=1" in result.output
        assert "+ meeting/kickoff.md" in result.output

    def test_inbox_ingest_skips_unchanged_on_second_run(self, inbox_dir, cli_env):
        (inbox_dir / "meeting" / "n.md").write_text(
            "# N\n\nbody", encoding="utf-8"
        )
        first = runner.invoke(cli_app, ["ingest", "inbox"])
        assert first.exit_code == 0, first.output

        second = runner.invoke(cli_app, ["ingest", "inbox"])
        assert second.exit_code == 0, second.output
        assert "ingested=0" in second.output
        assert "skipped=1" in second.output

    def test_inbox_ingest_handles_edits_as_updates(self, inbox_dir, cli_env):
        path = inbox_dir / "meeting" / "n.md"
        path.write_text("# N\n\nv1", encoding="utf-8")
        runner.invoke(cli_app, ["ingest", "inbox"])

        path.write_text("# N\n\nv2 changed", encoding="utf-8")
        result = runner.invoke(cli_app, ["ingest", "inbox"])

        assert result.exit_code == 0, result.output
        assert "updated=1" in result.output
        assert "~ meeting/n.md" in result.output

    def test_inbox_ingest_errors_when_inbox_dir_unset(
        self, tmp_sqlite_db, monkeypatch
    ):
        monkeypatch.setenv("CH_PROFILE", "quickstart")
        monkeypatch.setenv("CH_SQLITE_DB", str(tmp_sqlite_db))
        monkeypatch.setenv(
            "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_sqlite_db}"
        )
        monkeypatch.delenv("CH_INBOX_DIR", raising=False)
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        import sys
        from context_hub.config.settings import Settings
        original = sys.modules["context_hub.config.settings"].settings  # type: ignore[attr-defined]
        new_settings = Settings()
        sys.modules["context_hub.config.settings"].settings = new_settings  # type: ignore[attr-defined]
        sys.modules["context_hub.config"].settings = new_settings  # type: ignore[attr-defined]
        # Restore on test exit via monkeypatch finaliser.
        monkeypatch.setattr(
            sys.modules["context_hub.config.settings"], "settings", new_settings
        )
        monkeypatch.setattr(
            sys.modules["context_hub.config"], "settings", new_settings
        )
        _ = original  # keep reference for clarity

        result = runner.invoke(cli_app, ["ingest", "inbox"])
        assert result.exit_code == 1
        assert "CH_INBOX_DIR is not set" in result.output

    def test_inbox_is_a_recognised_source(self):
        result = runner.invoke(cli_app, ["ingest", "totally-fake"])
        assert result.exit_code != 0
        # Make sure the help text now lists inbox as a valid source
        # (the error message echoes the SOURCES tuple).
        assert "inbox" in result.output

    def test_gmail_is_a_recognised_source(self):
        result = runner.invoke(cli_app, ["ingest", "totally-fake"])
        assert result.exit_code != 0
        assert "gmail" in result.output
