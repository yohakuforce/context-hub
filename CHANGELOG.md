# Changelog

All notable changes to Context-Hub will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

_No unreleased changes yet._

---

## [0.3.1] - 2026-06-17

### Fixed

- **Admin GUI auth via `.env`** — the documented `init → serve → /admin` flow left every GUI data call `401`: the auth middleware read `DEV_API_KEY` from the environment at import time, but `init` only wrote it to `.env`. `serve` now loads the cwd `.env` into the process env before the app/auth import, and the auth middleware falls back to reading `os.environ` at request time, so a key loaded after import is still honored.
- **fp16 default is now device-aware** — half precision has no CPU kernel, so on the common GPU-less (e.g. Windows) box it was silently emulated, running *slower* and emitting warnings. `BGEM3EmbeddingAdapter` now defaults `use_fp16` on only for CUDA; override with the constructor arg or the `EMBEDDING_USE_FP16` env var.

### Added

- **Inbox `doc/` priority subdir** — the inbox watcher now also scans `<inbox_dir>/doc/`, listed *first* so high-value synthesized / converted (PPT/Excel→markdown) documents embed ahead of the raw long tail on slow CPU-only embedding boxes. `doc/` maps to `SourceType.FILE` with a `doc/<rel>` external-id prefix, so it never collides with `file/` on the upsert key.

---

## [0.3.0] - 2026-06-03

### Added — Admin GUI & serve-resident automation

- **Admin GUI at `/admin`** — a server-rendered, build-free console to configure
  everything that previously required `.env`/CLI edits, with three tabs:
  - **Settings**: read/write all connection settings & secrets via
    `GET/PUT /api/v1/config`. Secrets are masked (last 4 chars); saving writes
    `.env` and hot-reloads non-restart values; restart-required fields are flagged.
  - **Sources**: project & source-config CRUD via new write endpoints
    (`POST /api/v1/projects`, `PUT/DELETE /projects/{id}`,
    `PUT/DELETE /projects/{id}/sources/{type}`, `GET /projects/detailed`) — fills
    the gap where projects could previously only be created by direct repo calls.
  - **Status**: `GET /api/v1/status` — profile, ingest mode, scheduler, auto-sync,
    vector-vs-FTS-only, inbox, per-project enabled sources.
  - **Connection test**: `POST /api/v1/config/test/{source}` — readiness check plus
    a live ping for Slack (auth.test) and Redmine (users/current.json).
  - All data endpoints require the ADMIN/WRITE scope; the page shell is localhost.


- **`context-hub ingest all`**: one command that syncs every *enabled* source for
  the project in a single run (Slack / Backlog / Redmine / Gmail), then scans the
  inbox folder when `CH_INBOX_DIR` is set. Disabled sources and non-adapter types
  (meeting/file) are skipped; a failure in one source is logged and the others
  continue (no abort). Prints a per-source result and a `succeeded=/failed=`
  summary. Intended as the single entry point for a scheduled job.
- **`examples/launchd/`**: ready-made macOS launchd agent that runs
  `context-hub ingest all` on a fixed interval (default 15 min) without requiring
  a long-running `serve` process, plus cron / systemd / Windows Task Scheduler
  equivalents.
- **Serve-resident automatic source sync**: `context-hub serve` now registers an
  APScheduler interval job for every *enabled* external source of every project
  and re-syncs each on its `syncInterval` (min 5 min) — full automation without an
  external scheduler. Toggle with `CH_SOURCE_SYNC_ENABLED` (default on). Job
  failures are isolated and never crash the scheduler. (Previously the
  per-source scheduler existed but was never wired into startup.)
- **Windows support / graceful FTS-only fallback**: when the interpreter's
  `sqlite3` cannot load the `sqlite-vec` extension (notably stock python.org
  Windows builds), Context-Hub now runs in degraded **FTS-only mode** instead of
  crashing — `migrate` skips the `vec0` table, ingestion and keyword search work,
  and only semantic vector search is disabled (logged clearly at startup). Full
  semantic search remains available via a conda/miniforge Python or the
  PostgreSQL `production` profile.

### Fixed

- **Docs corrected**: `context-hub serve` has no `--http-only` flag — default is
  the HTTP REST API, `--mcp-only` runs the stdio MCP server. README / architecture
  docs updated to match the actual CLI.

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

### Added

- **会議メモ → タスク自動抽出**: 会議ドキュメント取込時に on-prem LLM
  （`LLM_PROVIDER` で選択。生トランスクリプトは外部に出さない）でアクションタスクを
  抽出し、ドキュメントに永続化。`GET /api/v1/projects/{projectId}/meetings/{meetingId}`
  と MCP `get_meeting` が `extractedTasks`（`title` / `suggestedAssignee` /
  `suggestedDueDate`）を返す。再読込でも結果は不変（取りこぼし防止）。
- **`POST /api/v1/projects/{projectId}/ingest/slack`**: 外部スクレイピング由来の
  Slack メッセージを `slack` ドキュメントとして冪等 upsert（Slack ts をキーに）。
  Slack API トークンなしで取り込めるパス。

### Fixed

- **SQLite プロファイルでの REST 全読み取りが 500 になる不具合**を修正。リポジトリ
  プロバイダを profile-aware 化し、SQLite 系では plain sqlite3 アダプタを使用
  （Postgres ORM が SQLite スキーマに無い列を SELECT していた）。配線ロックテスト追加。

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
