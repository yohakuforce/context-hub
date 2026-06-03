# Context-Hub

[![PyPI version](https://img.shields.io/pypi/v/yohakuforce-context-hub.svg)](https://pypi.org/project/yohakuforce-context-hub/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/yohakuforce/context-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/yohakuforce/context-hub/actions/workflows/ci.yml)

**MCP-native context collection and storage for AI-assisted software projects.**

Context-Hub collects project context (Slack messages, Backlog/Redmine issues, meeting notes) into a local SQLite or PostgreSQL store and exposes it over MCP (Model Context Protocol) and a REST API. AI agents such as Claude Desktop and Claude Code connect to it to answer questions about your project without sending raw data to third-party services.

---

## What is this?

| Feature | Detail |
|---|---|
| **MCP server** | stdio transport — plug directly into Claude Desktop or Claude Code |
| **REST API** | FastAPI — for custom integrations and web UIs |
| **Hybrid search** | Vector (sqlite-vec / pgvector) + FTS5 keyword search, RRF fusion |
| **Meeting → tasks** | On-prem LLM extracts action tasks from meeting transcripts **at ingest time** and persists them; `get_meeting` returns `extractedTasks` (stable across reads) |
| **Slack scraping ingest** | `POST /projects/{id}/ingest/slack` upserts scraped Slack messages (idempotent on `ts`) — no Slack API token required |
| **camelCase contract** | All REST responses are camelCase (consumed by AI-Project-Manager / @yohakuforce/core) |
| **Three profiles** | `quickstart` (SQLite + mock), `personal` (SQLite + BGE-M3), `production` (PostgreSQL) |
| **Zero-dependency start** | `pipx install` then `context-hub serve` — no Docker, no Postgres, no API keys required |

---

**Looking for the full operator guide?** See [`docs/usage-guide.md`](docs/usage-guide.md) — covers profiles, all five ingest paths, querying, ops, and privacy.

## Quick Start (60 seconds)

```bash
# Install
pipx install yohakuforce-context-hub

# Initialise with the zero-dependency quickstart profile
context-hub init --profile quickstart

# Apply database schema
context-hub migrate

# Start the HTTP REST API server (use --mcp-only for the stdio MCP server)
context-hub serve
```

Then query it:

```bash
# REST
curl http://127.0.0.1:8000/health
# {"status":"ok"}

# MCP version check (used by AI-PM at startup)
curl http://127.0.0.1:8000/mcp/version
# {"mcp_protocol_version":"2024-11-05","server":"context-hub","server_version":"0.3.0"}
```

Add to Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "context-hub": {
      "command": "context-hub",
      "args": ["serve", "--mcp-only"],
      "env": {
        "CONTEXT_HUB_API_KEY": "your-api-key"
      }
    }
  }
}
```

---

## Profiles

| Profile | Database | Embedding | Scheduler | Use case |
|---|---|---|---|---|
| `quickstart` | SQLite (file) | mock (hash-based) | in-memory | Zero-dependency local dev |
| `personal` | SQLite (file) | BGE-M3* | SQLite | Single-user persistent storage |
| `production` | PostgreSQL | BGE-M3* | PostgreSQL | Production deployment |

*BGE-M3 requires: `pip install 'yohakuforce-context-hub[embedding]'` (~2.3 GB model download on first run)

Switch profiles:

```bash
context-hub init --profile personal   # or production
context-hub migrate
context-hub serve
```

---

## Admin GUI

Prefer clicking to editing `.env`? Start the server and open the admin console:

```bash
context-hub serve            # HTTP REST API (the admin UI rides on it)
open http://127.0.0.1:8000/admin
```

It's a single server-rendered page (no build step), **in Japanese**, styled to
match the yohakuforce docs (paper/crimson theme). Every setting has an inline,
collapsible guide — **なぜ必要 (why) / 取得手順 (how to obtain) / 設定方法 (how to
set)** — so you never have to leave the screen to figure out where a token comes
from. Three tabs:

- **Settings** — every connection setting and secret (Slack / Backlog / Redmine /
  Gmail / LLM / embedding / DB / inbox …). Secrets are shown masked (last 4 chars);
  saving writes `.env` and hot-reloads non-restart values. Fields that need a
  restart are badged.
- **Sources** — create projects and configure each source (enable, sync interval,
  Slack channel IDs, Backlog/Redmine keys) without touching the database directly.
  Each source has a **Test** button (readiness + a live ping for Slack/Redmine).
- **Status** — profile, ingest mode, scheduler, auto-sync, vector-search vs
  FTS-only, inbox folder, and per-project enabled sources.

**Auth:** the page shell loads unauthenticated (bind to `127.0.0.1`), but every
data call requires an **ADMIN** API key you paste once (stored in the browser).
In development (the `quickstart` / `personal` profiles) that's the `DEV_API_KEY`
value — **`context-hub init` generates one for you and prints it** (it's also
saved in your `.env`). Grab it from the `init` output, or run
`grep DEV_API_KEY .env`, and paste it when the GUI prompts. In `production`
(`APP_ENV=production`) `DEV_API_KEY` is ignored — mint an ADMIN consumer key
instead (see [SECURITY.md](SECURITY.md)). The backing endpoints are
`GET/PUT /api/v1/config`, `POST /api/v1/config/test/{source}`,
`GET /api/v1/status`, and the project/source CRUD under `/api/v1/projects`.

> Run the admin UI on localhost only. It reads and writes credentials.

## Windows support

Context-Hub runs on Windows. One platform nuance to know:

- **`pip install` works** — all dependencies (including `sqlite-vec`) ship Windows wheels.
- **SQLite profiles auto-degrade to FTS-only when needed.** The official
  python.org Windows build of Python compiles `sqlite3` *without* loadable-extension
  support, so the `sqlite-vec` extension can't load there. When that happens,
  Context-Hub automatically runs in **FTS-only mode**: `migrate`, ingestion, and
  **keyword search all work** — only semantic (vector) search is disabled. A clear
  warning is logged at startup. (In the `quickstart` profile the default embedding
  is a meaningless hash, so you lose nothing real there.)
- **Want full semantic search on Windows?** Either:
  1. Use a Python that has loadable sqlite extensions — **conda / miniforge** Python
     does — then the SQLite profiles get full vector search; or
  2. Use the **`production` profile (PostgreSQL + pgvector)**, which doesn't use
     `sqlite-vec` at all and is fully featured on any Python.
- **Scheduling:** use Windows Task Scheduler to run `context-hub ingest all`, or
  just keep `context-hub serve` running (its built-in scheduler auto-syncs). See
  [`examples/launchd/README.md`](examples/launchd/README.md) for the Task Scheduler recipe.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Context-Hub Process                │
│                                                     │
│  ┌──────────────┐    ┌──────────────────────────┐  │
│  │  MCP Server  │    │     FastAPI REST API      │  │
│  │  (stdio)     │    │  /api/v1/{projects,query} │  │
│  └──────┬───────┘    └───────────┬──────────────┘  │
│         │                        │                  │
│         └───────────┬────────────┘                  │
│                     ▼                               │
│              QueryService (shared)                  │
│         VectorStore + FTS + RRF fusion              │
│                     │                               │
│         ┌───────────┴───────────┐                   │
│         ▼                       ▼                   │
│   SQLite (sqlite-vec)    PostgreSQL (pgvector)       │
│   SchedulerStore         SchedulerStore             │
└─────────────────────────────────────────────────────┘
```

Both MCP and HTTP layers are thin adapters over the shared `QueryService`. Neither layer owns business logic.

### Data Sources

Ingestion adapters collect context and write to the store:

- **Slack** — messages and threads (mock or live via `slack-sdk`)
- **Backlog** — issues and wiki (mock or live)
- **Redmine** — issues and wiki (mock or live)
- **Gmail** — labelled messages via the Gmail API (mock or live, opt-in extra)
- **Manual ingest** — `POST /api/v1/documents` for meeting notes, memos, email bodies, or any text the user wants to inject (see below)

### Manual document ingest

There are two ways to feed user-authored context (meeting notes, memos, email bodies, ...) into Context-Hub:

#### A. Inbox folder watcher (recommended for daily use)

Set `CH_INBOX_DIR` and drop files into the matching subdirectory. A background job scans every `CH_INBOX_POLL_SECONDS` (default 60) and upserts each file as a Document. **No commands to run, no API to call** — just save the file.

```bash
# .env (or shell)
CH_INBOX_DIR=~/.context-hub/inbox
CH_INBOX_POLL_SECONDS=60
# CH_PROJECT_ID=...   # required only if more than one project exists in the repo
```

Layout (Context-Hub is 1:1 with a project — no per-project subfolder needed):

```
~/.context-hub/inbox/
  meeting/
    2026-05-20-weekly.md
    2026/05/20-detail.md      # nested subdirs are fine
  file/
    product-spec.md
  email/
    saved-thread.txt
```

Rules:
- **Accepted extensions: `.md` and `.txt` only.** PDF / PowerPoint / docx must be converted to Markdown by the user before being dropped in.
- The first Markdown `# H1` is used as the title; otherwise the filename stem is used.
- `external_id = "<source_type>/<relative_path>"`. Editing a file in place upserts the existing document; unchanged files are skipped (no embedding cost).
- Hidden files (`.DS_Store` etc.) and unknown subdirectories are ignored.
- When `CH_INBOX_DIR` is unset, the watcher is disabled.

#### B. Direct REST call (for integrations and one-offs)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H "X-Api-Key: $CONTEXT_HUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj-001",
    "source_type": "meeting",
    "title": "2026-05-20 weekly",
    "text": "Decision: ship bundle plan A. Owner: koya. Next: ...",
    "external_id": "meeting-2026-05-20",
    "author": "koya"
  }'
```

`source_type` accepts `meeting | file | email`. Slack/Backlog/Redmine content must go through their dedicated `/sources/*/sync` endpoints. Re-posting with the same `external_id` upserts (replaces) the prior document. Omit `external_id` for a fresh insert each call.

#### C. File upload (.md / .txt / .pdf / .docx)

For documents that already live as files on disk (contracts, specs, exported meeting notes), POST them as multipart form data:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -H "X-Api-Key: $CONTEXT_HUB_API_KEY" \
  -F "project_id=proj-001" \
  -F "source_type=file" \
  -F "file=@./specs/project-phase1.pdf"
```

Accepted extensions: `.md`, `.txt` (always), and `.pdf`, `.docx` (only when the `[documents]` extra is installed):

```bash
pip install 'yohakuforce-context-hub[documents]'
```

- Max file size: **10 MiB**. Larger files return `413`.
- Server-side text extraction: pymupdf for PDF, python-docx for DOCX, UTF-8 decode for `.md`/`.txt`.
- `external_id` defaults to the filename, so re-uploading the same file replaces the prior document.
- Scanned PDFs without OCR cannot be ingested (no extractable text) — convert to OCR'd PDF first, or paste the text via the `/documents` endpoint.

Check what your install supports:

```bash
curl -H "X-Api-Key: $CONTEXT_HUB_API_KEY" \
  http://127.0.0.1:8000/api/v1/documents/upload/supported-extensions
```

### Gmail ingest

Pull labelled messages straight from Gmail into Context-Hub via the Gmail API.

**Why label-based by default?** The default query `label:context-hub` is explicit opt-in — only emails you tag with the `context-hub` label are ingested, so private mail stays out of the store. Override with any Gmail search syntax if you need broader coverage.

Setup:

```bash
# 1. Install the optional Google dependencies
pip install 'yohakuforce-context-hub[gmail]'

# 2. In Google Cloud Console, create an OAuth 2.0 Desktop client and download
#    credentials.json. Enable the Gmail API for the project.
# 3. Save credentials.json somewhere local, e.g. ~/.context-hub/gmail/credentials.json

# 4. Configure .env
GMAIL_CREDENTIALS_FILE=~/.context-hub/gmail/credentials.json
GMAIL_TOKEN_FILE=~/.context-hub/gmail/token.json
GMAIL_QUERY=label:context-hub          # override as needed
INGEST_MODE=live                       # mock by default; flip to live to hit Gmail

# 5. First run opens a browser for consent; the refresh token is then cached in
#    GMAIL_TOKEN_FILE and used for subsequent syncs.
context-hub ingest gmail --mode live
```

Trigger a sync via the API or CLI:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/sources/gmail/sync \
  -H "X-Api-Key: $CONTEXT_HUB_API_KEY" -H "Content-Type: application/json" \
  -d '{"project_id":"proj-001"}'
```

For scheduled sync, add an EMAIL `SourceConfig` to the Project (same pattern as Slack/Backlog/Redmine). The watcher uses the cursor mechanism to pull only newer messages on each tick.

### Settings Profiles (ADR-003)

Three `pydantic-settings` profiles inherit from a common base. Override any field with environment variables:

```
CH_PROFILE=quickstart   # default
CH_PROFILE=personal
CH_PROFILE=production
```

---

## CLI Reference

```
context-hub init     --profile [quickstart|personal|production]
context-hub migrate  [--dry-run] [--target HEAD] [--yes]
context-hub serve    [--host 127.0.0.1] [--port 8000] [--mcp-only] [--reload]
                     # default: HTTP REST API. --mcp-only: stdio MCP server instead.
context-hub ingest   [slack|backlog|redmine|gmail|inbox|all] [--mode mock|live]
context-hub query    "<text>" [--top-k 5] [--json] [--project-id <uuid>]
```

### One-shot full sync — `ingest all`

`context-hub ingest all` syncs **every enabled source** for the project in a
single run (Slack / Backlog / Redmine / Gmail), then scans the inbox folder when
`CH_INBOX_DIR` is set. A failure in one source is logged and the rest continue,
so one bad credential never blocks the others:

```bash
CH_PROFILE=personal INGEST_MODE=live context-hub ingest all
# Ingest-all: project_id='…', 2 enabled source(s), mode=live.
#   + slack: status=completed items=12
#   + backlog: status=completed items=3
# Ingest-all complete. project_id='…' succeeded=2 failed=0
```

This is the command to put on a schedule. See
[`examples/launchd/`](examples/launchd/) for a ready-made launchd agent (macOS)
that runs `ingest all` every 15 minutes, plus cron / systemd / Windows Task
Scheduler equivalents.

### Automatic background sync while `serve` runs

You don't even need an external scheduler if you keep `context-hub serve`
running: on startup it registers an interval job for **every enabled source** of
every project and re-syncs each on its `syncInterval` (minimum 5 minutes). The
inbox folder watcher runs the same way. This is on by default; disable it with:

```bash
CH_SOURCE_SYNC_ENABLED=false   # in .env or the environment
```

Pick **one** automation strategy: the built-in `serve` scheduler (simplest if the
server is always up) **or** an external `ingest all` job (durable across reboots
without keeping `serve` running). Running both just syncs twice.

---

## Optional Extras

```bash
# BGE-M3 local embedding (personal / production profiles)
pip install 'yohakuforce-context-hub[embedding]'

# PostgreSQL support
pip install 'yohakuforce-context-hub[postgres]'

# Gmail live ingest (OAuth2 + Gmail API)
pip install 'yohakuforce-context-hub[gmail]'

# PDF / DOCX upload extraction (pymupdf + python-docx)
pip install 'yohakuforce-context-hub[documents]'

# All
pip install 'yohakuforce-context-hub[embedding,postgres,gmail,documents]'
```

---

## Docker

See [`examples/docker/`](examples/docker/) for Docker Compose configuration.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

---

## License

Apache-2.0 — see [LICENSE](LICENSE).

---

## 日本語セクション

Context-Hub は AI 支援ソフトウェア開発プロジェクト向けの MCP ネイティブなコンテキスト収集・保存基盤です。

Slack / Backlog / Redmine などのプロジェクトデータをローカルの SQLite または PostgreSQL に集約し、MCP (Model Context Protocol) と REST API の両方で公開します。Claude Desktop や Claude Code などの AI エージェントが直接接続し、プロジェクト固有の情報に基づいた回答を生成します。

### 特徴

- **MCP 一級市民**: stdio トランスポートで Claude Desktop / Claude Code から直接利用可能
- **ハイブリッド検索**: ベクトル検索 (sqlite-vec / pgvector) + FTS5 全文検索を RRF でフュージョン
- **ゼロ依存スタート**: `pipx install` のみで動作開始、Docker 不要、Postgres 不要
- **3 プロファイル**: quickstart (SQLite + mock)、personal (SQLite + BGE-M3)、production (PostgreSQL)

### クイックスタート

```bash
pipx install yohakuforce-context-hub
context-hub init --profile quickstart
context-hub migrate
context-hub serve
```
