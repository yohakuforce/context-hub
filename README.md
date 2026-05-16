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
# {"mcp_protocol_version":"2024-11-05","server":"context-hub","server_version":"0.1.0"}
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
context-hub ingest   [slack|backlog|redmine] [--mode mock|live]
context-hub query    "<text>" [--top-k 5] [--json] [--project-id <uuid>]
```

---

## Optional Extras

```bash
# BGE-M3 local embedding (personal / production profiles)
pip install 'yohakuforce-context-hub[embedding]'

# PostgreSQL support
pip install 'yohakuforce-context-hub[postgres]'

# Both
pip install 'yohakuforce-context-hub[embedding,postgres]'
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
