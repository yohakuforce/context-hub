# Changelog

All notable changes to Context-Hub will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- `--yes` / `-y` flag for `migrate` command to skip production confirmation prompt

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
