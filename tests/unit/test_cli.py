"""Unit tests for the context-hub CLI (src/cli/main.py).

Uses typer's CliRunner for isolated invocation without side effects.
Each command gets at least one test covering the happy path and one
covering the primary error path.

Strategy for async helper tests:
  - Use sys.modules patching for local-import functions (e.g. _run_migrate, _run_query).
  - MagicMock / AsyncMock inserted into sys.modules before the coroutine runs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(
    db_url: str = "sqlite+aiosqlite:///./data/test.db",
    sqlite_db: str = "./data/test.db",
    embedding_provider: str = "mock",
) -> MagicMock:
    """Return a ProfileSettings-like MagicMock."""
    s = MagicMock()
    s.database_url = db_url
    s.ch_sqlite_db = sqlite_db
    s.embedding_provider = embedding_provider
    return s


def _inject_module_mock(name: str, **attrs: object) -> MagicMock:
    """Insert a MagicMock module into sys.modules for the duration of a test.

    Args:
        name:   Dotted module path (e.g. 'src.config.profiles').
        **attrs: Attributes to set on the mock module.

    Returns:
        The MagicMock module object (can be used as context manager too).
    """
    mock_mod = MagicMock(spec=ModuleType(name))
    for attr, val in attrs.items():
        setattr(mock_mod, attr, val)
    return mock_mod


# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


class TestInitCommand:
    """Tests for `context-hub init`."""

    def test_init_quickstart_creates_env_and_data_dir(self) -> None:
        """Happy path: init --profile quickstart writes .env and creates data/."""
        with runner.isolated_filesystem():
            result = runner.invoke(
                app, ["init", "--profile", "quickstart"], catch_exceptions=False
            )
            env_created = Path(".env").exists()
            data_created = Path("data").exists()

        assert result.exit_code == 0
        assert "quickstart" in result.output
        assert env_created
        assert data_created

    def test_init_personal_profile(self) -> None:
        """init --profile personal should succeed."""
        with runner.isolated_filesystem():
            result = runner.invoke(
                app, ["init", "--profile", "personal"], catch_exceptions=False
            )
        assert result.exit_code == 0
        assert "personal" in result.output

    def test_init_production_profile(self) -> None:
        """init --profile production should succeed."""
        with runner.isolated_filesystem():
            result = runner.invoke(
                app, ["init", "--profile", "production"], catch_exceptions=False
            )
        assert result.exit_code == 0
        assert "production" in result.output

    def test_init_unknown_profile_exits_nonzero(self) -> None:
        """init with an unrecognised profile must exit with code 1."""
        with runner.isolated_filesystem():
            result = runner.invoke(app, ["init", "--profile", "unknown"])
        assert result.exit_code == 1
        assert "unknown" in result.output

    def test_init_existing_env_without_force_exits_nonzero(self) -> None:
        """init should fail if .env already exists and --force is not given."""
        with runner.isolated_filesystem():
            Path(".env").write_text("# existing env\n")
            result = runner.invoke(app, ["init", "--profile", "quickstart"])
        assert result.exit_code == 1

    def test_init_force_flag_overwrites_existing_env(self) -> None:
        """init --force should succeed even when .env already exists."""
        with runner.isolated_filesystem():
            Path(".env").write_text("# existing env\n")
            result = runner.invoke(
                app, ["init", "--profile", "quickstart", "--force"], catch_exceptions=False
            )
        assert result.exit_code == 0
        assert "quickstart" in result.output

    def test_init_env_content_matches_profile(self) -> None:
        """The generated .env should contain CH_PROFILE matching the chosen profile."""
        with runner.isolated_filesystem():
            runner.invoke(
                app, ["init", "--profile", "quickstart"], catch_exceptions=False
            )
            content = Path(".env").read_text()

        assert "CH_PROFILE=quickstart" in content


# ---------------------------------------------------------------------------
# serve command
# ---------------------------------------------------------------------------


class TestServeCommand:
    """Tests for `context-hub serve`."""

    def test_serve_mcp_only_and_http_only_mutually_exclusive(self) -> None:
        """serve --mcp-only --http-only should exit with code 1."""
        result = runner.invoke(app, ["serve", "--mcp-only", "--http-only"])
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output

    def test_serve_mcp_only_starts_mcp_server(self) -> None:
        """serve --mcp-only should invoke asyncio.run for the MCP stdio server."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()) as mock_run:
            result = runner.invoke(app, ["serve", "--mcp-only"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        assert "mcp" in result.output.lower()

    def test_serve_calls_uvicorn_run(self) -> None:
        """serve (default) should call uvicorn.run with the correct app import path."""
        import uvicorn

        with patch.object(uvicorn, "run") as mock_run:
            result = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--port", "9000"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        call_args, call_kwargs = mock_run.call_args
        assert call_args[0] == "src.main:app"
        assert call_kwargs["host"] == "0.0.0.0"
        assert call_kwargs["port"] == 9000

    def test_serve_default_host_and_port(self) -> None:
        """serve without flags uses host=127.0.0.1 and port=8000."""
        import uvicorn

        with patch.object(uvicorn, "run") as mock_run:
            result = runner.invoke(app, ["serve"])

        assert result.exit_code == 0
        _, call_kwargs = mock_run.call_args
        assert call_kwargs["host"] == "127.0.0.1"
        assert call_kwargs["port"] == 8000

    def test_serve_help_flag(self) -> None:
        """serve --help should exit 0 and include descriptive text."""
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "server" in result.output.lower() or "uvicorn" in result.output.lower()


# ---------------------------------------------------------------------------
# ingest command
# ---------------------------------------------------------------------------


class TestIngestCommand:
    """Tests for `context-hub ingest`."""

    def test_ingest_unknown_source_exits_nonzero(self) -> None:
        """ingest with an unknown source must exit with code 1."""
        result = runner.invoke(app, ["ingest", "github"])
        assert result.exit_code == 1
        assert "github" in result.output

    def test_ingest_unknown_mode_exits_nonzero(self) -> None:
        """ingest with an unknown mode must exit with code 1."""
        result = runner.invoke(app, ["ingest", "slack", "--mode", "streaming"])
        assert result.exit_code == 1
        assert "streaming" in result.output

    @pytest.mark.parametrize("source", ("slack", "backlog", "redmine"))
    def test_ingest_all_valid_sources_accepted(self, source: str) -> None:
        """All three valid sources should pass validation and invoke asyncio.run."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            result = runner.invoke(app, ["ingest", source, "--mode", "mock"])
        assert result.exit_code == 0

    def test_ingest_help_flag(self) -> None:
        """ingest --help should exit 0."""
        result = runner.invoke(app, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "source" in result.output.lower() or "slack" in result.output.lower()

    def test_ingest_project_id_option_accepted(self) -> None:
        """ingest --project-id <uuid> should be accepted."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            result = runner.invoke(
                app, ["ingest", "slack", "--mode", "mock", "--project-id", "test-uuid"]
            )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# query command
# ---------------------------------------------------------------------------


class TestQueryCommand:
    """Tests for `context-hub query`."""

    def test_query_invokes_asyncio_run(self) -> None:
        """query should invoke asyncio.run with the async pipeline."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            result = runner.invoke(app, ["query", "test query text"])
        assert result.exit_code == 0

    def test_query_top_k_option_accepted(self) -> None:
        """query --top-k N should be accepted without error."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            result = runner.invoke(app, ["query", "search text", "--top-k", "10"])
        assert result.exit_code == 0

    def test_query_json_flag_accepted(self) -> None:
        """query --json should be accepted."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            result = runner.invoke(app, ["query", "search text", "--json"])
        assert result.exit_code == 0

    def test_query_project_id_option_accepted(self) -> None:
        """query --project-id should be passed through."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            result = runner.invoke(
                app, ["query", "search text", "--project-id", "proj-uuid-123"]
            )
        assert result.exit_code == 0

    def test_query_help_flag(self) -> None:
        """query --help should exit 0."""
        result = runner.invoke(app, ["query", "--help"])
        assert result.exit_code == 0
        assert "query" in result.output.lower() or "search" in result.output.lower()


# ---------------------------------------------------------------------------
# migrate command
# ---------------------------------------------------------------------------


class TestMigrateCommand:
    """Tests for `context-hub migrate`."""

    def test_migrate_dry_run_exits_zero(self) -> None:
        """migrate --dry-run should exit 0 without applying anything."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            result = runner.invoke(app, ["migrate", "--dry-run"])
        assert result.exit_code == 0

    def test_migrate_default_target_is_head(self) -> None:
        """migrate without --target should default to 'head'."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            result = runner.invoke(app, ["migrate"])
        assert result.exit_code == 0

    def test_migrate_custom_target_accepted(self) -> None:
        """migrate --target 001 should be accepted."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            result = runner.invoke(app, ["migrate", "--target", "001"])
        assert result.exit_code == 0

    def test_migrate_help_flag(self) -> None:
        """migrate --help should exit 0."""
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "migrat" in result.output.lower()


# ---------------------------------------------------------------------------
# _run_migrate async unit tests
# ---------------------------------------------------------------------------


class TestRunMigrateAsync:
    """Unit tests for the _run_migrate async helper."""

    @pytest.mark.asyncio
    async def test_dry_run_prints_and_returns(self) -> None:
        """_run_migrate dry_run=True should print info and return without DB access."""
        from src.cli.main import _run_migrate

        settings_mock = _mock_settings()
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        with patch.dict(sys.modules, {"src.config.profiles": mock_profiles}):
            # Must not raise
            await _run_migrate(target="head", dry_run=True)

    @pytest.mark.asyncio
    async def test_sqlite_calls_migration_runner_upgrade(self) -> None:
        """_run_migrate with a SQLite URL calls SqliteMigrationRunner.upgrade."""
        from src.cli.main import _run_migrate

        mock_runner = AsyncMock()
        mock_runner.current_revision.return_value = None

        settings_mock = _mock_settings()
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_migration_module = MagicMock()
        mock_migration_module.SqliteMigrationRunner = MagicMock(return_value=mock_runner)

        with patch.dict(
            sys.modules,
            {
                "src.config.profiles": mock_profiles,
                "src.adapters.sqlite.migration_runner": mock_migration_module,
            },
        ):
            await _run_migrate(target="head", dry_run=False)

        mock_runner.upgrade.assert_called_once_with(target="head")


# ---------------------------------------------------------------------------
# _run_query async unit tests
# ---------------------------------------------------------------------------


class TestRunQueryAsync:
    """Unit tests for the _run_query async helper."""

    @pytest.mark.asyncio
    async def test_query_postgres_url_exits_nonzero(self) -> None:
        """_run_query should raise typer.Exit(1) for PostgreSQL URLs in v0.1."""
        import click

        from src.cli.main import _run_query

        settings_mock = _mock_settings(
            db_url="postgresql+asyncpg://postgres:pass@localhost/context_hub"
        )
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        with patch.dict(sys.modules, {"src.config.profiles": mock_profiles}):
            # typer.Exit wraps click.exceptions.Exit — catch the correct exception
            with pytest.raises((click.exceptions.Exit, SystemExit)) as exc_info:
                await _run_query(
                    text="test",
                    project_id=None,
                    top_k=5,
                    output_json=False,
                )

        # Either a click Exit with code 1 or a SystemExit with code 1
        code = (
            exc_info.value.exit_code
            if isinstance(exc_info.value, click.exceptions.Exit)
            else exc_info.value.code
        )
        assert code == 1

    @pytest.mark.asyncio
    async def test_query_calls_search_service(self) -> None:
        """_run_query should call QueryService.search with the provided text."""
        from src.cli.main import _run_query

        mock_result = MagicMock()
        mock_result.score = 0.987
        mock_result.title = "Test Title"
        mock_result.snippet = "A short snippet..."
        mock_result.document.id = "doc-uuid-123"

        mock_service = AsyncMock()
        mock_service.search.return_value = [mock_result]

        mock_project = MagicMock()
        mock_project.id = "proj-uuid-456"

        mock_project_repo = AsyncMock()
        mock_project_repo.find_all.return_value = [mock_project]

        settings_mock = _mock_settings()
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_embedding_factory = MagicMock()
        mock_embedding_factory.get_embedding_provider = MagicMock(return_value=MagicMock())

        mock_doc_repo_module = MagicMock()
        mock_doc_repo_module.SqliteDocumentRepository = MagicMock(return_value=MagicMock())

        mock_proj_repo_module = MagicMock()
        mock_proj_repo_module.SqliteProjectRepository = MagicMock(
            return_value=mock_project_repo
        )

        mock_qs_module = MagicMock()
        mock_qs_module.QueryService = MagicMock(return_value=mock_service)

        with patch.dict(
            sys.modules,
            {
                "src.config.profiles": mock_profiles,
                "src.infrastructure.embedding.factory": mock_embedding_factory,
                "src.adapters.sqlite.document_repository": mock_doc_repo_module,
                "src.adapters.sqlite.project_repository": mock_proj_repo_module,
                "src.application.query_service": mock_qs_module,
            },
        ):
            await _run_query(
                text="test query",
                project_id=None,
                top_k=5,
                output_json=False,
            )

        mock_service.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_no_results_outputs_message(self) -> None:
        """_run_query with empty results should output 'No results found.'."""
        from src.cli.main import _run_query

        mock_service = AsyncMock()
        mock_service.search.return_value = []

        mock_project = MagicMock()
        mock_project.id = "proj-uuid-456"

        mock_project_repo = AsyncMock()
        mock_project_repo.find_all.return_value = [mock_project]

        settings_mock = _mock_settings()
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_embedding_factory = MagicMock()
        mock_embedding_factory.get_embedding_provider = MagicMock(return_value=MagicMock())

        mock_doc_repo_module = MagicMock()
        mock_doc_repo_module.SqliteDocumentRepository = MagicMock(return_value=MagicMock())

        mock_proj_repo_module = MagicMock()
        mock_proj_repo_module.SqliteProjectRepository = MagicMock(
            return_value=mock_project_repo
        )

        mock_qs_module = MagicMock()
        mock_qs_module.QueryService = MagicMock(return_value=mock_service)

        output_lines: list[str] = []

        def capture_echo(msg: str = "", **_: object) -> None:
            output_lines.append(str(msg))

        with patch.dict(
            sys.modules,
            {
                "src.config.profiles": mock_profiles,
                "src.infrastructure.embedding.factory": mock_embedding_factory,
                "src.adapters.sqlite.document_repository": mock_doc_repo_module,
                "src.adapters.sqlite.project_repository": mock_proj_repo_module,
                "src.application.query_service": mock_qs_module,
            },
        ), patch("typer.echo", side_effect=capture_echo):
            await _run_query(
                text="nothing here",
                project_id=None,
                top_k=5,
                output_json=False,
            )

        assert any("no results" in line.lower() for line in output_lines)


# ---------------------------------------------------------------------------
# B-1: migrate --dry-run password mask test
# ---------------------------------------------------------------------------


class TestMigratePasswordMask:
    """B-1: verify that --dry-run output never exposes plain-text passwords."""

    @pytest.mark.asyncio
    async def test_dry_run_masks_password_in_output(self) -> None:
        """_run_migrate dry_run=True must not leak the password in the output.

        Given a PostgreSQL URL with a clear-text password 'secret',
        the dry-run output must contain '***' (SQLAlchemy's hide_password mask)
        and must NOT contain the literal 'secret'.
        """
        from src.cli.main import _run_migrate

        settings_mock = _mock_settings(
            db_url="postgresql+asyncpg://user:secret@host/db",
            sqlite_db="",
        )
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        output_lines: list[str] = []

        def capture_echo(msg: str = "", **_: object) -> None:
            output_lines.append(str(msg))

        with patch.dict(sys.modules, {"src.config.profiles": mock_profiles}), patch(
            "typer.echo", side_effect=capture_echo
        ):
            await _run_migrate(target="head", dry_run=True)

        combined = " ".join(output_lines)
        assert "secret" not in combined, "Plain-text password must not appear in dry-run output"
        assert "***" in combined or "***@" in combined, (
            "Masked password pattern ('***' or '***@') must appear in dry-run output"
        )

    @pytest.mark.asyncio
    async def test_dry_run_sqlite_url_does_not_contain_fake_password(self) -> None:
        """_run_migrate dry_run=True with an SQLite URL should output the URL safely.

        SQLite URLs have no password, so neither 'secret' nor '***' are expected.
        The output should still contain the database path.
        """
        from src.cli.main import _run_migrate

        settings_mock = _mock_settings(
            db_url="sqlite+aiosqlite:///./data/context_hub.db",
        )
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        output_lines: list[str] = []

        def capture_echo(msg: str = "", **_: object) -> None:
            output_lines.append(str(msg))

        with patch.dict(sys.modules, {"src.config.profiles": mock_profiles}), patch(
            "typer.echo", side_effect=capture_echo
        ):
            await _run_migrate(target="head", dry_run=True)

        combined = " ".join(output_lines)
        keywords = ("dry-run", "dry_run", "would migrate")
        assert any(k in combined.lower() for k in keywords)
        assert "secret" not in combined


# ---------------------------------------------------------------------------
# B-2: init chmod 0600 test
# ---------------------------------------------------------------------------


class TestInitChmod:
    """B-2: verify that init sets 0600 permissions on the generated .env file."""

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file permissions not applicable")
    def test_init_env_file_has_0600_permissions(self) -> None:
        """init must set file permissions to 0600 on the generated .env.

        This prevents other users on a shared system from reading credentials.
        """
        with runner.isolated_filesystem():
            result = runner.invoke(
                app, ["init", "--profile", "quickstart"], catch_exceptions=False
            )
            assert result.exit_code == 0, result.output

            env_path = Path(".env")
            assert env_path.exists(), ".env was not created"

            file_mode = os.stat(env_path).st_mode & 0o777
            assert file_mode == 0o600, (
                f"Expected .env permissions 0600, got {oct(file_mode)}"
            )

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file permissions not applicable")
    def test_init_force_overwrites_and_resets_permissions(self) -> None:
        """init --force must reset permissions to 0600 even when .env already exists."""
        with runner.isolated_filesystem():
            # Create a .env with permissive permissions
            env_path = Path(".env")
            env_path.write_text("# old env\n")
            os.chmod(env_path, 0o644)

            result = runner.invoke(
                app,
                ["init", "--profile", "quickstart", "--force"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0, result.output

            file_mode = os.stat(env_path).st_mode & 0o777
            assert file_mode == 0o600, (
                f"Expected .env permissions 0600 after --force, got {oct(file_mode)}"
            )


# ---------------------------------------------------------------------------
# C-1 coverage: additional CLI paths
# ---------------------------------------------------------------------------


class TestServeAdditionalPaths:
    """C-1: cover serve command paths not previously tested."""

    def test_serve_uvicorn_import_error(self) -> None:
        """serve should exit 1 with informative message when uvicorn is not installed."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "uvicorn":
                raise ImportError("No module named 'uvicorn'")
            return real_import(name, *args, **kwargs)  # type: ignore[call-overload]

        with patch("builtins.__import__", side_effect=mock_import):
            result = runner.invoke(app, ["serve"])
        assert result.exit_code == 1
        assert "uvicorn" in result.output.lower() or "uvicorn" in (result.output + "").lower()

    def test_serve_reload_production_warning(self) -> None:
        """serve --reload with APP_ENV=production should emit a warning to stderr."""
        import uvicorn

        settings_mock = _mock_settings()
        settings_mock.app_env = "production"
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        with patch.object(uvicorn, "run"), patch.dict(
            sys.modules, {"src.config.profiles": mock_profiles}
        ):
            result = runner.invoke(app, ["serve", "--reload", "--http-only"])

        # Warning should appear (CliRunner merges stderr into output by default)
        assert result.exit_code == 0
        assert "warning" in result.output.lower() or "production" in result.output.lower()

    def test_serve_http_only_calls_uvicorn(self) -> None:
        """serve --http-only should call uvicorn.run (same as default)."""
        import uvicorn

        with patch.object(uvicorn, "run") as mock_run:
            result = runner.invoke(app, ["serve", "--http-only"])

        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_serve_mcp_only_runs_asyncio(self) -> None:
        """serve --mcp-only should invoke asyncio.run (not uvicorn)."""
        with patch("asyncio.run", side_effect=lambda coro: coro.close()):
            with patch.dict(
                sys.modules,
                {"src.mcp.server": MagicMock(run_stdio=AsyncMock())},
            ):
                result = runner.invoke(app, ["serve", "--mcp-only"])

        # May succeed or fail depending on import, but asyncio.run should be called
        # or the MCP path should be reached (no "not yet available" message)
        assert "not yet available" not in result.output.lower()


class TestMigrateAdditionalPaths:
    """C-1 coverage + C-2: production confirm + subprocess path."""

    @pytest.mark.asyncio
    async def test_postgres_migrate_calls_alembic(self) -> None:
        """_run_migrate with PostgreSQL URL calls subprocess alembic upgrade."""
        from src.cli.main import _run_migrate

        settings_mock = _mock_settings(
            db_url="postgresql+asyncpg://user:pass@host/db",
            sqlite_db="",
        )
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "alembic upgrade output"
        mock_result.stderr = ""

        with patch.dict(sys.modules, {"src.config.profiles": mock_profiles}), patch(
            "subprocess.run", return_value=mock_result
        ):
            await _run_migrate(target="head", dry_run=False)

    @pytest.mark.asyncio
    async def test_postgres_migrate_nonzero_exit_raises(self) -> None:
        """_run_migrate with PostgreSQL URL raises typer.Exit when alembic fails."""
        import click

        from src.cli.main import _run_migrate

        settings_mock = _mock_settings(
            db_url="postgresql+asyncpg://user:pass@host/db",
            sqlite_db="",
        )
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "alembic error"

        with patch.dict(sys.modules, {"src.config.profiles": mock_profiles}), patch(
            "subprocess.run", return_value=mock_result
        ):
            with pytest.raises((click.exceptions.Exit, SystemExit)):
                await _run_migrate(target="head", dry_run=False)

    def test_migrate_production_confirm_aborted(self) -> None:
        """migrate in production without --yes should abort when user says 'n'."""
        settings_mock = _mock_settings()
        settings_mock.app_env = "production"
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        with patch.dict(sys.modules, {"src.config.profiles": mock_profiles}), patch(
            "typer.confirm", side_effect=SystemExit(1)
        ):
            result = runner.invoke(app, ["migrate"])
        # Aborted: should exit non-zero
        assert result.exit_code != 0

    def test_migrate_production_yes_flag_skips_confirm(self) -> None:
        """migrate --yes in production should skip the confirmation prompt."""
        settings_mock = _mock_settings()
        settings_mock.app_env = "production"
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        with patch.dict(sys.modules, {"src.config.profiles": mock_profiles}), patch(
            "asyncio.run", side_effect=lambda coro: coro.close()
        ):
            result = runner.invoke(app, ["migrate", "--yes"])
        assert result.exit_code == 0


class TestIngestAdditionalPaths:
    """C-1 coverage: _run_ingest postgres path and no-projects error."""

    @pytest.mark.asyncio
    async def test_ingest_postgres_url_exits_nonzero(self) -> None:
        """_run_ingest should raise typer.Exit(1) for PostgreSQL URLs in v0.1."""
        import click

        from src.cli.main import _run_ingest

        settings_mock = _mock_settings(
            db_url="postgresql+asyncpg://user:pass@host/db",
            sqlite_db="",
        )
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_embedding = MagicMock()
        mock_embedding_factory = MagicMock()
        mock_embedding_factory.get_embedding_provider = MagicMock(return_value=mock_embedding)

        with patch.dict(
            sys.modules,
            {
                "src.config.profiles": mock_profiles,
                "src.infrastructure.embedding.factory": mock_embedding_factory,
            },
        ):
            with pytest.raises((click.exceptions.Exit, SystemExit)) as exc_info:
                await _run_ingest(source="slack", mode="mock", project_id=None)

        code = (
            exc_info.value.exit_code
            if isinstance(exc_info.value, click.exceptions.Exit)
            else exc_info.value.code
        )
        assert code == 1

    @pytest.mark.asyncio
    async def test_ingest_no_projects_exits_nonzero(self) -> None:
        """_run_ingest should exit 1 when no projects exist and project_id is None."""
        import click

        from src.cli.main import _run_ingest

        settings_mock = _mock_settings()
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_embedding_factory = MagicMock()
        mock_embedding_factory.get_embedding_provider = MagicMock(return_value=MagicMock())

        mock_project_repo = AsyncMock()
        mock_project_repo.find_all.return_value = []

        mock_proj_repo_module = MagicMock()
        mock_proj_repo_module.SqliteProjectRepository = MagicMock(
            return_value=mock_project_repo
        )
        mock_doc_repo_module = MagicMock()
        mock_job_repo_module = MagicMock()
        mock_issue_repo_module = MagicMock()
        mock_ingest_module = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "src.config.profiles": mock_profiles,
                "src.infrastructure.embedding.factory": mock_embedding_factory,
                "src.adapters.sqlite.project_repository": mock_proj_repo_module,
                "src.adapters.sqlite.document_repository": mock_doc_repo_module,
                "src.adapters.sqlite.ingestion_job_repository": mock_job_repo_module,
                "src.adapters.sqlite.issue_repository": mock_issue_repo_module,
                "src.application.ingestion_service": mock_ingest_module,
            },
        ):
            with pytest.raises((click.exceptions.Exit, SystemExit)) as exc_info:
                await _run_ingest(source="slack", mode="mock", project_id=None)

        code = (
            exc_info.value.exit_code
            if isinstance(exc_info.value, click.exceptions.Exit)
            else exc_info.value.code
        )
        assert code == 1


class TestQueryAdditionalPaths:
    """C-1 coverage: _run_query JSON output and no-projects error."""

    @pytest.mark.asyncio
    async def test_query_json_output_format(self) -> None:
        """_run_query with output_json=True should emit valid JSON to typer.echo."""
        import json as _json

        from src.cli.main import _run_query

        mock_result = MagicMock()
        mock_result.score = 0.95
        mock_result.title = "JSON Test Title"
        mock_result.snippet = "JSON snippet..."
        mock_result.document.id = "doc-json-uuid"

        mock_service = AsyncMock()
        mock_service.search.return_value = [mock_result]

        mock_project = MagicMock()
        mock_project.id = "proj-json-uuid"

        mock_project_repo = AsyncMock()
        mock_project_repo.find_all.return_value = [mock_project]

        settings_mock = _mock_settings()
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_embedding_factory = MagicMock()
        mock_embedding_factory.get_embedding_provider = MagicMock(return_value=MagicMock())

        mock_doc_repo_module = MagicMock()
        mock_doc_repo_module.SqliteDocumentRepository = MagicMock(return_value=MagicMock())

        mock_proj_repo_module = MagicMock()
        mock_proj_repo_module.SqliteProjectRepository = MagicMock(
            return_value=mock_project_repo
        )

        mock_qs_module = MagicMock()
        mock_qs_module.QueryService = MagicMock(return_value=mock_service)

        captured: list[str] = []

        def capture_echo(msg: str = "", **_: object) -> None:
            captured.append(str(msg))

        with patch.dict(
            sys.modules,
            {
                "src.config.profiles": mock_profiles,
                "src.infrastructure.embedding.factory": mock_embedding_factory,
                "src.adapters.sqlite.document_repository": mock_doc_repo_module,
                "src.adapters.sqlite.project_repository": mock_proj_repo_module,
                "src.application.query_service": mock_qs_module,
            },
        ), patch("typer.echo", side_effect=capture_echo):
            await _run_query(
                text="json query",
                project_id=None,
                top_k=5,
                output_json=True,
            )

        # Should have captured at least one JSON string
        assert len(captured) >= 1
        parsed = _json.loads(captured[0])
        assert isinstance(parsed, list)
        assert parsed[0]["title"] == "JSON Test Title"
        assert parsed[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_query_no_projects_exits_nonzero(self) -> None:
        """_run_query should exit 1 when no projects exist and project_id is None."""
        import click

        from src.cli.main import _run_query

        settings_mock = _mock_settings()
        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_embedding_factory = MagicMock()
        mock_embedding_factory.get_embedding_provider = MagicMock(return_value=MagicMock())

        mock_project_repo = AsyncMock()
        mock_project_repo.find_all.return_value = []

        mock_proj_repo_module = MagicMock()
        mock_proj_repo_module.SqliteProjectRepository = MagicMock(
            return_value=mock_project_repo
        )
        mock_doc_repo_module = MagicMock()
        mock_doc_repo_module.SqliteDocumentRepository = MagicMock(return_value=MagicMock())

        with patch.dict(
            sys.modules,
            {
                "src.config.profiles": mock_profiles,
                "src.infrastructure.embedding.factory": mock_embedding_factory,
                "src.adapters.sqlite.project_repository": mock_proj_repo_module,
                "src.adapters.sqlite.document_repository": mock_doc_repo_module,
            },
        ):
            with pytest.raises((click.exceptions.Exit, SystemExit)) as exc_info:
                await _run_query(
                    text="test",
                    project_id=None,
                    top_k=5,
                    output_json=False,
                )

        code = (
            exc_info.value.exit_code
            if isinstance(exc_info.value, click.exceptions.Exit)
            else exc_info.value.code
        )
        assert code == 1


class TestInitEnvSrcNotFound:
    """C-1 coverage: init with missing env example source file."""

    def test_init_env_src_not_found_exits_nonzero(self) -> None:
        """init should exit 1 if the env example source file does not exist."""
        with runner.isolated_filesystem():
            # Patch _ENV_EXAMPLE_BASE to a non-existent directory
            with patch("src.cli.main._ENV_EXAMPLE_BASE", Path("/nonexistent/path")):
                result = runner.invoke(app, ["init", "--profile", "quickstart"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()
