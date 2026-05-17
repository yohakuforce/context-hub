# Changelog

All notable changes to Context-Hub will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

(no unreleased changes)

---

## [0.1.0] - 2026-05-17

Initial stable OSS release.

### Added
- MCP server as first-class entry point (`context-hub serve --mcp-only`)
- `MCP_PROTOCOL_VERSION` constant exported from `context_hub/mcp/__init__.py`
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

### Changed
- **Namespace refactor (T-20260516-007a)**: renamed top-level package `src/` → `context_hub/`.
  Import paths updated from `from src.X` to `from context_hub.X`. Entry point changed from
  `src.cli.main:app` to `context_hub.cli.main:main`. No logic changes; purely mechanical rename.
- **Packaging — bundled resources**: relocated `examples/env/.env.example.{quickstart,personal,production}`
  to `context_hub/_env_examples/` and `schema/sqlite/001_init.sql` to
  `context_hub/_sqlite_schema/001_init.sql` so they ship inside the wheel.
- **Lazy DB engine**: `context_hub.infrastructure.db.session` now creates the SQLAlchemy
  async engine on first access (PEP 562 `__getattr__`), instead of at import time. This
  unblocks SQLite-only installs that don't have asyncpg.
- **`SqliteMigrationRunner.upgrade()` fail-loud**: raises `FileNotFoundError` if the
  schema directory is missing, instead of silently returning. This surfaced a packaging
  bug during smoke tests.
- **`.gitignore` narrowed**: `*.sql` → `data/**/*.sql` and `dumps/**/*.sql` so future
  bundled schema files cannot be silently dropped.

### Dependencies
- Promoted to core: `numpy>=1.26`, `aiosqlite>=0.20.0`, `pgvector>=0.3.0`,
  `sqlalchemy[asyncio]>=2.0.0`.
- Pinned `apscheduler>=3.10.0,<4.0` — apscheduler 4.x removed the
  `apscheduler.schedulers` namespace.
- `asyncpg` and `pgvector` added to `[dev]` extras so CI can collect postgres-backend
  test modules.

### Fixed
- mypy `no-any-return` error in `context_hub.adapters.sqlite.vec_store._to_blob`.

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
