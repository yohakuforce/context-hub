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

# Start server (HTTP + MCP stdio on the same process)
context-hub serve
```

Then query it:

```bash
# REST
curl http://127.0.0.1:8000/health
# {"status":"ok","env":"development"}

# MCP version check (used by AI-PM at startup)
curl http://127.0.0.1:8000/mcp/version
# {"mcp_protocol_version":"2024-11-05","server":"context-hub","server_version":"0.2.0"}
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
context-hub serve    [--host 127.0.0.1] [--port 8000]
                     [--mcp-only | --http-only]
                     [--reload]
context-hub ingest   [slack|backlog|redmine|gmail|inbox] [--mode mock|live]
context-hub query    "<text>" [--top-k 5] [--json] [--project-id <uuid>]
```

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
