# Changelog

All notable changes to Context-Hub will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed — BREAKING: REST 応答が camelCase に統一

- 全 API 応答の JSON キーを **camelCase** に統一（`02-api-spec.md` の契約に準拠）。
  従来は実装が snake_case を返しており、仕様書・コンシューマ(AI-Project-Manager /
  @yohakuforce/core)が期待する camelCase と食い違っていた。
  - 例: `project_id` → `projectId`, `external_id` → `externalId`,
    `source_type` → `sourceType`, `document_count` → `documentCount`
  - 全 wire スキーマを `CamelModel` 基底（`alias_generator=to_camel`,
    `populate_by_name=True`）に統一。**リクエストは snake_case も後方互換で受理**。
  - 契約ロックテスト追加: `tests/unit/api/test_schema_camelcase_contract.py`
- **影響**: 既存の snake_case 応答に依存する外部コンシューマは要修正。
  次回リリースは破壊的変更のため **v0.3.0** を想定（公開タイミングは別途判断）。

---

## [0.2.0] - 2026-05-20

User-authored context, file uploads, Gmail, and a folder-drop ingest workflow.

### Added
- **`POST /api/v1/documents`** — manual text ingest (meeting notes, memos, email bodies).
  Accepts `source_type` of `meeting | file | email`; Slack/Backlog/Redmine continue to
  go through their dedicated `/sources/*/sync` endpoints. Upserts by
  `(project_id, source_type, external_id)`.
- **Inbox folder watcher** — drop `.md` / `.txt` files into
  `$CH_INBOX_DIR/{meeting,file,email}/` and they are upserted on a polling
  interval (default 60s). Editing a file replaces the prior document; unchanged
  files are skipped (no re-embedding cost). Single-project deployments resolve
  the target project automatically; multi-project deployments pin via
  `CH_PROJECT_ID`.
- **`context-hub ingest inbox`** — one-shot CLI scan of the inbox folder, sharing
  the same code path as the polling watcher.
- **Gmail adapter** — `POST /api/v1/sources/gmail/sync`, `context-hub ingest gmail`,
  and scheduled sync via a `SourceConfig` with `source_type=EMAIL`. OAuth2 with
  refresh-token caching; default query `label:context-hub` is label-based opt-in
  to keep private mail out of the index. Lives behind the new `[gmail]` extra.
- **`POST /api/v1/documents/upload`** — multipart file upload for
  `.md` / `.txt` / `.pdf` / `.docx`. Max 10 MiB; PDF and DOCX text extraction
  requires the new `[documents]` extra (pymupdf + python-docx).
- **`GET /api/v1/documents/upload/supported-extensions`** — reports which
  extensions the running install accepts.
- **`docs/usage-guide.md`** — full operator guide covering profiles, ingest
  paths, querying, ops, and privacy.

### Changed
- Mock fixtures are now bundled with the wheel at `context_hub/_fixtures/`
  (previously `tests/fixtures/`). `INGEST_MODE=mock` now works in installed
  environments — earlier alphas would `FileNotFoundError` after `pipx install`.
- `.env.example` references the correct profile template path and uses the
  `context-hub serve` entry point. Per-profile `.env.example.*` files document
  the new Gmail and inbox-watcher knobs.
- Lifespan tests migrated from the deprecated
  `asyncio.get_event_loop().run_until_complete()` pattern to `asyncio.run()`
  for resilience against test ordering.

### Fixed
- `InMemoryDocumentRepository` (test fake) now mirrors the production contract
  by upserting on the `(project_id, source_type, external_id)` composite key
  rather than `id` alone.
- Stale references to `examples/env/...` and `uvicorn src.main:app` in
  `.env.example` corrected.

### Privacy
- Test fixtures and example filenames scrubbed of project-specific identifiers.

### Extras (optional pip extras)
- `[gmail]` — `google-api-python-client`, `google-auth`, `google-auth-oauthlib`,
  `google-auth-httplib2`. Required only for live Gmail ingest.
- `[documents]` — `pymupdf`, `python-docx`. Required only for `.pdf` / `.docx`
  upload extraction.

### Upgrade Notes
- Wire format and storage schema are unchanged from v0.1.0; existing SQLite /
  PostgreSQL databases keep working.
- New environment variables (all optional): `CH_INBOX_DIR`,
  `CH_INBOX_POLL_SECONDS`, `CH_PROJECT_ID`, `GMAIL_CREDENTIALS_FILE`,
  `GMAIL_TOKEN_FILE`, `GMAIL_QUERY`.

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
