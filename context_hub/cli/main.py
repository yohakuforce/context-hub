"""Context-Hub CLI — typer-based command-line interface.

Entry point: context-hub

Commands:
    init     Generate .env and data/ directory for a given profile.
    serve    Start the FastAPI / MCP server via uvicorn.
    ingest   Trigger a one-shot ingestion run for a given source.
    query    Run a hybrid search query and print results.
    migrate  Apply pending database migrations.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="context-hub",
    help="Context-Hub: MCP-native context collection and storage for AI projects.",
    no_args_is_help=True,
    add_completion=False,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROFILES = ("quickstart", "personal", "production")
SOURCES = ("slack", "backlog", "redmine")
INGEST_MODES = ("mock", "live")

_ENV_EXAMPLE_BASE = Path(__file__).parent.parent.parent / "examples" / "env"


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@app.command()
def init(
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            "-p",
            help="Backend profile to initialise: quickstart | personal | production.",
        ),
    ] = "quickstart",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite existing .env file if present.",
        ),
    ] = False,
) -> None:
    """Initialise .env and data/ directory for the given profile.

    Copies the profile-specific env example file to .env in the current
    working directory and creates the data/ directory if it does not exist.

    Profiles:
      quickstart  — SQLite + mock embedding (zero external dependencies)
      personal    — SQLite + BGE-M3 embedding (single-user, no Postgres)
      production  — PostgreSQL + BGE-M3 embedding (full feature set)
    """
    if profile not in PROFILES:
        typer.echo(
            f"Error: unknown profile '{profile}'. "
            f"Valid options: {', '.join(PROFILES)}",
            err=True,
        )
        raise typer.Exit(code=1)

    env_dest = Path(".env")
    env_src = _ENV_EXAMPLE_BASE / f".env.example.{profile}"

    if env_dest.exists() and not force:
        typer.echo(
            ".env already exists. Use --force to overwrite.",
            err=True,
        )
        raise typer.Exit(code=1)

    if not env_src.exists():
        typer.echo(
            f"Error: env example file not found: {env_src}",
            err=True,
        )
        raise typer.Exit(code=1)

    shutil.copy(env_src, env_dest)
    os.chmod(env_dest, 0o600)
    typer.echo(f"Wrote .env from profile '{profile}' (permissions: 600).")

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    typer.echo("Ensured data/ directory exists.")

    typer.echo("")
    typer.echo("Next steps:")
    if profile == "quickstart":
        typer.echo("  context-hub migrate")
        typer.echo("  context-hub serve")
    elif profile == "personal":
        typer.echo("  1. Edit .env and set SLACK_BOT_TOKEN / BACKLOG_API_KEY if needed.")
        typer.echo("  2. pip install 'yohakuforce-context-hub[embedding]'")
        typer.echo("  3. context-hub migrate && context-hub serve")
    else:
        typer.echo("  1. Edit .env and set DATABASE_URL, SECRET_KEY, and API keys.")
        typer.echo("  2. pip install 'yohakuforce-context-hub[embedding]'")
        typer.echo("  3. context-hub migrate")
        typer.echo("  4. context-hub serve")


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@app.command()
def serve(
    host: Annotated[
        str,
        typer.Option("--host", help="Bind address for the HTTP server."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="TCP port for the HTTP server."),
    ] = 8000,
    mcp_only: Annotated[
        bool,
        typer.Option(
            "--mcp-only",
            help="Start MCP stdio transport only (no HTTP REST API).",
        ),
    ] = False,
    reload: Annotated[
        bool,
        typer.Option("--reload", help="Enable uvicorn hot-reload (development only)."),
    ] = False,
) -> None:
    """Start the Context-Hub server.

    Default: HTTP REST API server (use --mcp-only for stdio MCP server).

    The server reads configuration from the .env file in the current working
    directory (or environment variables directly).
    """
    if mcp_only:
        import asyncio

        from context_hub.mcp.server import run_stdio

        typer.echo("Starting Context-Hub MCP server (stdio transport) ...")
        asyncio.run(run_stdio())
        return

    try:
        import uvicorn
    except ImportError:
        typer.echo(
            "Error: uvicorn is required. Install it with: pip install 'uvicorn[standard]'",
            err=True,
        )
        raise typer.Exit(code=1)

    # Warn if --reload is used in production
    from context_hub.config.profiles import get_profile_settings

    try:
        _settings = get_profile_settings()
        if reload and _settings.app_env == "production":
            typer.echo(
                "Warning: --reload is enabled in production mode. "
                "This is not recommended for production deployments.",
                err=True,
            )
    except Exception:  # noqa: BLE001
        pass  # Do not block startup if settings cannot be loaded

    typer.echo(f"Starting Context-Hub HTTP server on http://{host}:{port} ...")
    uvicorn.run(
        "context_hub.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


@app.command()
def ingest(
    source: Annotated[
        str,
        typer.Argument(help="Data source to ingest: slack | backlog | redmine."),
    ],
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help="Ingest mode: mock (fixture data) or live (real API).",
        ),
    ] = "mock",
    project_id: Annotated[
        str | None,
        typer.Option(
            "--project-id",
            help="Target project UUID. Required when multiple projects exist.",
        ),
    ] = None,
) -> None:
    """Trigger a one-shot ingestion run for the given source.

    Supported sources:
      slack    — Fetch messages from the configured Slack workspace.
      backlog  — Fetch issues from the configured Backlog project.
      redmine  — Fetch issues from the configured Redmine instance.

    Modes:
      mock  — Use fixture data (no real API keys required).
      live  — Call the real API using credentials from .env.
    """
    if source not in SOURCES:
        typer.echo(
            f"Error: unknown source '{source}'. "
            f"Valid options: {', '.join(SOURCES)}",
            err=True,
        )
        raise typer.Exit(code=1)

    if mode not in INGEST_MODES:
        typer.echo(
            f"Error: unknown mode '{mode}'. "
            f"Valid options: {', '.join(INGEST_MODES)}",
            err=True,
        )
        raise typer.Exit(code=1)

    import asyncio

    asyncio.run(_run_ingest(source=source, mode=mode, project_id=project_id))


async def _run_ingest(source: str, mode: str, project_id: str | None) -> None:
    """Async implementation for the ingest command.

    Args:
        source:     Source type: slack | backlog | redmine.
        mode:       Ingest mode: mock | live.
        project_id: Optional project UUID override.
    """
    from context_hub.config.profiles import get_profile_settings
    from context_hub.infrastructure.embedding.factory import get_embedding_provider

    settings = get_profile_settings()
    profile = os.environ.get("CH_PROFILE", "quickstart")
    typer.echo(f"Ingesting from '{source}' (mode={mode}, profile={profile}) ...")

    db_url = settings.database_url
    if "sqlite" not in db_url:
        typer.echo(
            "Error: CLI ingest is only supported for SQLite profiles in v0.1. "
            "For PostgreSQL, use the HTTP API (POST /api/v1/sync).",
            err=True,
        )
        raise typer.Exit(code=1)

    db_path = settings.ch_sqlite_db or "./data/context_hub.db"
    embedding_provider = get_embedding_provider(settings.embedding_provider)

    from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
    from context_hub.adapters.sqlite.ingestion_job_repository import SqliteIngestionJobRepository
    from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
    from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
    from context_hub.application.ingestion_service import IngestionService

    project_repo = SqliteProjectRepository(db_path)
    document_repo = SqliteDocumentRepository(db_path)
    issue_repo = SqliteIssueRepository(db_path)
    job_repo = SqliteIngestionJobRepository(db_path)

    resolved_pid = project_id
    if resolved_pid is None:
        projects = await project_repo.find_all()
        if not projects:
            typer.echo(
                "Error: no projects found. Create a project first via POST /api/v1/projects.",
                err=True,
            )
            raise typer.Exit(code=1)
        resolved_pid = str(projects[0].id)

    from context_hub.infrastructure.adapters.base import SourceAdapter
    from context_hub.shared.types import ProjectId

    adapter: SourceAdapter = _build_adapter(  # type: ignore[assignment]
        source=source, mode=mode, settings=settings
    )
    service = IngestionService(
        adapter=adapter,
        embedding_provider=embedding_provider,
        job_repo=job_repo,
        document_repo=document_repo,
        issue_repo=issue_repo,
    )
    await service.run(project_id=ProjectId(resolved_pid))
    typer.echo(f"Ingestion complete. source='{source}', project_id={resolved_pid!r}")


def _build_adapter(source: str, mode: str, settings: object) -> object:
    """Instantiate the correct SourceAdapter for *source* and *mode*.

    Args:
        source:   Source type string: slack | backlog | redmine.
        mode:     Ingest mode: mock | live.
        settings: ProfileSettings instance.

    Returns:
        A SourceAdapter protocol-compatible object.
    """
    if source == "slack":
        from context_hub.infrastructure.adapters.slack.adapter import SlackAdapter

        return SlackAdapter(
            bot_token=getattr(settings, "slack_bot_token", None) or "dummy-token",
            channel_ids=[],
            ingest_mode=mode,
        )
    if source == "backlog":
        from context_hub.infrastructure.adapters.backlog.adapter import BacklogAdapter

        return BacklogAdapter(
            space_key=getattr(settings, "backlog_space_key", None) or "dummy-space",
            api_key=getattr(settings, "backlog_api_key", None) or "dummy-key",
            backlog_project_key="",
            include_wiki=False,
            ingest_mode=mode,
        )
    # source == "redmine"
    from context_hub.infrastructure.adapters.redmine.adapter import RedmineAdapter

    return RedmineAdapter(
        base_url=getattr(settings, "redmine_base_url", None) or "http://localhost:3000",
        api_key=getattr(settings, "redmine_api_key", None) or "dummy-key",
        redmine_project_identifier="",
        include_wiki=False,
        ingest_mode=mode,
    )


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


@app.command()
def query(
    text: Annotated[
        str,
        typer.Argument(help="Search query text."),
    ],
    project_id: Annotated[
        str | None,
        typer.Option(
            "--project-id",
            help="Project UUID to search within.",
        ),
    ] = None,
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Maximum number of results to return."),
    ] = 5,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Output results as JSON."),
    ] = False,
) -> None:
    """Run a hybrid search query and print the results.

    Embeds the query text and performs a hybrid (vector + full-text) search
    against the document store for the given project.

    Example:
        context-hub query "deployment checklist" --project-id <uuid> --top-k 10
    """
    import asyncio

    asyncio.run(
        _run_query(
            text=text,
            project_id=project_id,
            top_k=top_k,
            output_json=output_json,
        )
    )


async def _run_query(
    text: str,
    project_id: str | None,
    top_k: int,
    output_json: bool,
) -> None:
    """Async implementation for the query command.

    Args:
        text:       Search query string.
        project_id: Optional project UUID filter.
        top_k:      Maximum number of results.
        output_json: If True, output as JSON; otherwise human-readable text.
    """
    import json as _json

    from context_hub.application.query_service import QueryService
    from context_hub.config.profiles import get_profile_settings
    from context_hub.infrastructure.embedding.factory import get_embedding_provider

    settings = get_profile_settings()
    db_url = settings.database_url

    if "sqlite" not in db_url:
        typer.echo(
            "Error: CLI query is only supported for SQLite profiles in v0.1. "
            "For PostgreSQL, use the HTTP API (GET /api/v1/query).",
            err=True,
        )
        raise typer.Exit(code=1)

    db_path = settings.ch_sqlite_db or "./data/context_hub.db"
    embedding_provider = get_embedding_provider(settings.embedding_provider)

    from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
    from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository

    project_repo = SqliteProjectRepository(db_path)
    document_repo = SqliteDocumentRepository(db_path)

    resolved_pid = project_id
    if resolved_pid is None:
        projects = await project_repo.find_all()
        if not projects:
            typer.echo(
                "Error: no projects found. Create a project first via POST /api/v1/projects.",
                err=True,
            )
            raise typer.Exit(code=1)
        resolved_pid = str(projects[0].id)

    from context_hub.shared.types import ProjectId

    service = QueryService(
        document_repo=document_repo,
        embedding_provider=embedding_provider,
    )
    results = await service.search(
        project_id=ProjectId(resolved_pid),
        query=text,
        top_k=top_k,
    )

    if output_json:
        data = [
            {
                "score": r.score,
                "title": r.title,
                "snippet": r.snippet,
                "document_id": str(r.document.id),
            }
            for r in results
        ]
        typer.echo(_json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if not results:
            typer.echo("No results found.")
            return
        typer.echo(f"Found {len(results)} result(s) for: '{text}'\n")
        for i, result in enumerate(results, start=1):
            typer.echo(f"[{i}] score={result.score:.4f}  {result.title}")
            typer.echo(f"    {result.snippet}")
            typer.echo("")


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


@app.command()
def migrate(
    target: Annotated[
        str,
        typer.Option(
            "--target",
            help="Revision to migrate to. 'head' applies all pending migrations.",
        ),
    ] = "head",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print what would be migrated without applying changes.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip confirmation prompt (for CI / non-interactive environments).",
        ),
    ] = False,
) -> None:
    """Apply pending database migrations.

    Automatically selects the correct migration runner based on the DATABASE_URL:
      sqlite+aiosqlite://  -> SqliteMigrationRunner (schema/sqlite/)
      postgresql+asyncpg:// -> Alembic (alembic.ini must be present)

    In production (APP_ENV=production), a confirmation prompt is shown unless
    --yes / -y is passed.

    Example:
        context-hub migrate
        context-hub migrate --target 001
        context-hub migrate --dry-run
        context-hub migrate --yes   # non-interactive (CI)
    """
    import asyncio

    # Production safety gate: require explicit confirmation unless --yes is passed.
    if not dry_run and not yes:
        try:
            from context_hub.config.profiles import get_profile_settings

            _settings = get_profile_settings()
            if _settings.app_env == "production":
                typer.confirm(
                    "You are about to apply migrations to a PRODUCTION database. Continue?",
                    abort=True,
                )
        except typer.Abort:
            typer.echo("Aborted.")
            raise typer.Exit(code=1)
        except Exception:  # noqa: BLE001
            pass  # If settings cannot be loaded, proceed without confirmation

    asyncio.run(_run_migrate(target=target, dry_run=dry_run))


async def _run_migrate(target: str, dry_run: bool) -> None:
    """Async implementation for the migrate command.

    Args:
        target:  Alembic-style revision target ("head" or a revision string).
        dry_run: If True, only print what would happen without applying changes.
    """
    from sqlalchemy.engine.url import make_url

    from context_hub.config.profiles import get_profile_settings

    settings = get_profile_settings()
    db_url = settings.database_url

    if dry_run:
        safe_url = make_url(db_url).render_as_string(hide_password=True)
        typer.echo(f"Dry-run: would migrate '{safe_url}' to target='{target}'.")
        return

    if "sqlite" in db_url:
        from context_hub.adapters.sqlite.migration_runner import SqliteMigrationRunner

        db_path = settings.ch_sqlite_db or "./data/context_hub.db"
        runner = SqliteMigrationRunner(db_path=db_path)
        current = await runner.current_revision()
        typer.echo(
            f"SQLite migration: db={db_path!r}, "
            f"current={current!r}, target={target!r}"
        )
        await runner.upgrade(target=target)
        new_rev = await runner.current_revision()
        typer.echo(f"Migration complete. Revision: {new_rev!r}")
    else:
        typer.echo(f"PostgreSQL migration: running alembic upgrade {target}")
        import subprocess  # noqa: S404

        result = subprocess.run(  # noqa: S603
            ["alembic", "upgrade", target],
            capture_output=True,
            text=True,
        )
        if result.stdout:
            typer.echo(result.stdout)
        if result.returncode != 0:
            typer.echo(result.stderr, err=True)
            raise typer.Exit(code=result.returncode)
        typer.echo("Alembic migration complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point called by the 'context-hub' script."""
    app()


if __name__ == "__main__":
    main()
