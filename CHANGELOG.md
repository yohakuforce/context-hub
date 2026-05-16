# Changelog

All notable changes to Context-Hub will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed
- **Namespace refactor (T-20260516-007a)**: renamed top-level package `src/` → `context_hub/`.
  All import paths updated from `from src.X` to `from context_hub.X`. Entry point changed from
  `src.cli.main:app` to `context_hub.cli.main:main`. No logic changes; purely mechanical rename.
- **Packaging fix (0.1.0a2)**: relocated `examples/env/.env.example.{quickstart,personal,production}`
  to `context_hub/_env_examples/` so they ship inside the wheel. Without this, `context-hub init`
  failed in installed packages with "env example file not found".
- **Lazy DB engine (0.1.0a3)**: `context_hub.infrastructure.db.session` now creates the
  SQLAlchemy async engine on first access (PEP 562 `__getattr__`), instead of at import
  time. Without this, importing the FastAPI app from a SQLite-profile install eagerly
  loaded the asyncpg dialect and crashed when asyncpg was not installed.

### Added
- `--yes` / `-y` flag for `migrate` command to skip production confirmation prompt
- Direct dependency on `numpy>=1.26` (was previously a transitive of `[embedding]` extras
  but is used by the core SQLite vector store on every install).
- Direct dependency on `aiosqlite>=0.20.0` (required for the default `sqlite+aiosqlite://`
  DATABASE_URL).
- Switched `sqlalchemy` to `sqlalchemy[asyncio]` (0.1.0a4) so `greenlet` is pulled in. Without it,
  importing `sqlalchemy.ext.asyncio` raises `ImportError` and `context-hub serve` fails to start.
- Added `asyncpg` and `pgvector` to `[dev]` extras so CI can collect the postgres-backend
  test modules (collection imports `context_hub.infrastructure.db.models`, which uses
  `pgvector.sqlalchemy.Vector` as a column type).
- **Bundled SQLite schema (0.1.0a5)**: relocated `schema/sqlite/001_init.sql` to
  `context_hub/_sqlite_schema/001_init.sql` so it ships in the wheel. The previous
  location was both outside the package AND gitignored by a broad `*.sql` rule, so
  `context-hub migrate` silently no-op'd on installed packages (the file was missing
  from CI checkouts and from every published wheel).
- `.gitignore` narrowed: `*.sql` → `data/**/*.sql` and `dumps/**/*.sql` so future
  schema files cannot be silently dropped.
- `SqliteMigrationRunner.upgrade()` now raises `FileNotFoundError` if the schema
  directory is missing, instead of silently returning (was the root cause of v0.1.0a3
  smoke test false-passing `migrate`).

### Fixed
- mypy `no-any-return` error in `context_hub.adapters.sqlite.vec_store._to_blob`.

---

## [0.1.0] - 2026-05-31

### Added
- MCP server as first-class entry point (`context-hub serve --mcp-only`)
- `MCP_PROTOCOL_VERSION` constant exported from `src/mcp/__init__.py`
- `/mcp/version` HTTP endpoint for AI-PM compatibility checks
- `--mcp-only` / `--http-only` flags for `serve` command (fully functional)
- Production safety gate: `migrate` prompts for confirmation in `APP_ENV=production`
- `--yes` / `-y` flag on `migrate` for CI/non-interactive environments
- `--reload` + `production` warning on `serve`
- Three-profile settings system: `quickstart`, `personal`, `production`
- Hybrid search: sqlite-vec (vector) + FTS5 (keyword) with RRF fusion
- Ingestion adapters: Slack, Backlog, Redmine (mock and live modes)
- APScheduler integration with three backends: memory, SQLite, PostgreSQL
- Repository pattern for all data access (Protocol-based)
- CLI: `init`, `serve`, `ingest`, `query`, `migrate`
- `examples/mcp/mcp.json` — Claude Desktop configuration template
- `examples/integrations/ai-pm/` — AI-PM integration guide and config
- Apache-2.0 license

### Security
- Removed authentication backdoor from P3 development phase
- `context-hub init` sets `.env` permissions to `0600`
- `migrate --dry-run` masks database passwords using SQLAlchemy `hide_password`

---

## [0.1.0a1] - 2026-05-16

### Added
- Initial alpha release
- Core domain model: `Project`, `Document`, `IngestionJob`, `Issue`
- SQLite adapter layer with sqlite-vec and FTS5
- PostgreSQL adapter layer with pgvector
- FastAPI REST API: `/api/v1/projects`, `/api/v1/query`, `/api/v1/sync`, `/api/v1/issues`
- Basic CLI scaffolding
- Docker Compose example

[Unreleased]: https://github.com/yohakuforce/context-hub/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yohakuforce/context-hub/compare/v0.1.0a1...v0.1.0
[0.1.0a1]: https://github.com/yohakuforce/context-hub/releases/tag/v0.1.0a1
