# Context-Hub Usage Guide

This guide walks through everyday operation: starting the server, adding context, querying it from your AI agent, and keeping things tidy. For high-level architecture see [`architecture.md`](./architecture.md). For installation and quickstart see the top-level [`README.md`](../README.md).

---

## 1. Mental model

Context-Hub is a **per-project context store**. The intended deployment is **one Context-Hub instance per project**:

```
Client project A → Context-Hub instance #1 → port 8001 → its own SQLite DB + inbox
Client project B → Context-Hub instance #2 → port 8002 → its own SQLite DB + inbox
Internal R&D     → Context-Hub instance #3 → port 8003 → its own SQLite DB + inbox
```

This isolation is intentional:

- **No cross-contamination**: a NDA-bound client's mail/Slack never reaches another project's index.
- **Simple permissions**: kill the process, archive the SQLite file, project is gone.
- **Cheap to spin up**: each instance is one Python process + one file.

Inside a single instance you can technically have multiple `Project` rows, but treating one Context-Hub as one project keeps everything (inbox watcher, Gmail filter, scheduler) trivially auto-routed.

---

## 2. Picking a profile

| Profile | DB | Embedding | When |
|---|---|---|---|
| `quickstart` | SQLite | mock (hash) | First 60 seconds, smoke tests, CI |
| `personal` | SQLite | BGE-M3 (local) | Daily solo use on a Mac mini or laptop |
| `production` | PostgreSQL | BGE-M3 | Multi-user deployments, durability matters |

Switch with `CH_PROFILE=personal` then `context-hub init --profile personal && context-hub migrate`.

The mock embedding is hash-based and gives meaningless semantic results — it exists so the install path works without downloading a 2.3 GB model. Move to `personal` once you actually want hybrid search to work.

---

## 2.5 Configuring with the Admin GUI (no `.env` editing)

If you'd rather click than edit `.env`, Context-Hub ships a server-rendered admin
console — no build step, in Japanese, served on localhost.

```bash
context-hub serve            # the admin UI rides on the HTTP server
open http://127.0.0.1:8000/admin
```

**Before you open it:** every data call in the GUI needs an **ADMIN** API key.
In the `quickstart` / `personal` profiles that's the `DEV_API_KEY` value —
`context-hub init` generates one and prints it (it's also in your `.env`; recover
it any time with `grep DEV_API_KEY .env`). Paste it once when the page prompts;
it's stored in your browser. In `production` (`APP_ENV=production`) `DEV_API_KEY`
is ignored — issue an ADMIN consumer key instead (see [SECURITY.md](../SECURITY.md)).

The console has three tabs:

| Tab | What you do there |
|---|---|
| **Settings** | Read/write every connection setting and secret (Slack / Backlog / Redmine / Gmail / LLM / embedding / DB / inbox). Secrets show masked; saving writes `.env` and hot-reloads non-restart values. Each field has an inline **why / how to obtain / how to set** guide, so you never leave the screen to find where a token comes from. |
| **Sources** | Create projects and configure each source (enable, sync interval, Slack channel IDs, Backlog/Redmine keys) without touching the database. Each source has a **Test** button (readiness + a live ping for Slack/Redmine). |
| **Status** | Profile, ingest mode, scheduler, serve-resident auto-sync, vector-search vs FTS-only, inbox folder, and per-project enabled sources at a glance. |

Everything here maps 1:1 to an `.env` key or REST endpoint — the GUI is a
convenience layer, not a separate config store. CLI/`.env` and the GUI stay in sync.

> Run the admin UI on localhost only (`--host 127.0.0.1`). It reads and writes credentials.

---

## 3. Feeding context in

There are five ways to put data into Context-Hub. Pick whichever matches the source.

| Source | Mechanism | Setup cost | Best for |
|---|---|---|---|
| Slack | `POST /sources/slack/sync` or scheduled | Bot token | Real-time team chat |
| Backlog / Redmine | `POST /sources/{backlog,redmine}/sync` | API key | Issue trackers |
| Gmail | `POST /sources/gmail/sync` or scheduled | OAuth2 + labels | Client correspondence |
| **Inbox folder** | Drop file into `CH_INBOX_DIR/{meeting,file,email}/` | None — env var only | Meeting notes, memos, anything text |
| **REST / Upload** | `POST /documents` (JSON) or `POST /documents/upload` (multipart) | None | Integrations, file imports |

Slack/Backlog/Redmine/Gmail are documented in the README. This section focuses on the two paths most users hit daily: inbox and upload.

### Inbox folder watcher

1. Set `CH_INBOX_DIR=~/.context-hub/inbox` in `.env`.
2. Create the subdirectories you need:

   ```
   ~/.context-hub/inbox/
     meeting/     ← meeting notes go here
     file/        ← arbitrary docs
     email/       ← saved email bodies
   ```

3. Drop `.md` or `.txt` files in. Within `CH_INBOX_POLL_SECONDS` (default 60) they appear in queries.

**Rules**:

- Only `.md` and `.txt` are accepted. PDF / DOCX → use the upload endpoint or convert to Markdown first.
- The first `# H1` becomes the title. If absent, the filename stem is used.
- Editing the file → next poll detects the diff → upserts (no duplicates).
- Hidden files (`.DS_Store`, dotfiles), other extensions, and unknown subdirectories are silently ignored.
- Nested subdirectories under `meeting/` etc. are scanned recursively — organise by date/topic however you like.

**One-shot scan** (skip the wait):

```bash
context-hub ingest inbox
```

This invokes the same scanner the polling job uses and prints a summary.

### File upload (.md / .txt / .pdf / .docx)

When you already have a file (a signed PDF contract, a Word memo, an exported transcript), upload it directly:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -H "X-Api-Key: $CONTEXT_HUB_API_KEY" \
  -F "project_id=$PROJECT_ID" \
  -F "source_type=file" \
  -F "file=@./contract-v2.pdf"
```

Install the extractor extras to enable PDF and DOCX:

```bash
pip install 'yohakuforce-context-hub[documents]'
```

Limits and caveats:

- **10 MiB max** per file — split larger documents.
- **No OCR**: scanned PDFs without a text layer return `400`.
- `external_id` defaults to the filename. Re-uploading `contract-v2.pdf` replaces the prior version.

---

## 4. Querying

All five ingest paths land in the same `Document` table, so a single query searches across everything.

### Via MCP (recommended for AI agents)

Configure Claude Desktop / Claude Code to point at your Context-Hub MCP stdio server (see README). Then ask the agent: *"What did the client decide in the kickoff?"* — it calls Context-Hub via MCP and gets relevant snippets back.

### Via REST

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "X-Api-Key: $CONTEXT_HUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj-001",
    "query": "kickoff decisions",
    "top_k": 5
  }'
```

Filter by source:

```json
{"project_id": "proj-001", "query": "見積", "top_k": 5, "source_types": ["email", "file"]}
```

### Via CLI

```bash
context-hub query "kickoff decisions" --top-k 5
context-hub query "見積" --top-k 5 --json
```

---

## 5. Operational notes

### Where state lives

| What | Where (quickstart / personal) |
|---|---|
| Documents, projects, jobs | `./data/context_hub.db` (SQLite) |
| Scheduler state | `./data/scheduler.db` (SQLite) |
| Gmail refresh token | `$GMAIL_TOKEN_FILE` (default unset — set it) |
| API keys (configured) | `.env` |

Back up `data/` and `.env` together; that's the entire state.

### Resetting a project

```bash
rm -rf data/
context-hub migrate
# Re-create your project via POST /api/v1/projects
```

### Multiple instances on one machine

Each instance needs:

- Its own `.env` (different `DATABASE_URL`, `CH_INBOX_DIR`, `GMAIL_QUERY`, `--port`)
- Its own data dir
- Its own working directory

Run them in separate terminals or via a process supervisor (launchd, systemd, pm2 — your choice).

### Logs

Server logs go to stdout in structured JSON via `structlog`. Pipe through `jq` for ad-hoc reading:

```bash
context-hub serve 2>&1 | jq -R 'fromjson? // .'
```

---

## 6. Privacy and data handling

Read this before pointing Context-Hub at sensitive sources.

- **All ingested text is stored locally**: SQLite file on your disk, or your Postgres instance. Nothing leaves the machine unless you explicitly configure an LLM provider that ships data out.
- **Embeddings are local** when you use the `bge-m3` provider. The default `mock` embedding is hash-based and trivially reversible, but `bge-m3` runs the entire pipeline offline.
- **API keys are not stored in the index** — they only authenticate requests. Rotate them by changing `.env` and restarting.
- **Gmail OAuth tokens** are stored in `GMAIL_TOKEN_FILE`. This file contains a refresh token that can read your inbox until you revoke it at https://myaccount.google.com/permissions. Treat it like a password: don't commit it.
- **Inbox folder contents** stay on disk where you placed them — Context-Hub only reads. If you delete a file from the inbox, the indexed Document remains until you delete it via the API.

### What to do if you accidentally ingest something sensitive

1. Stop the server.
2. Look up the document: `GET /api/v1/projects/{id}/context` (or query for it).
3. Delete it directly from the SQLite DB or run `rm -rf data/` for a full reset.
4. If a Gmail label is involved, remove the label in Gmail and run a `full_resync` so the cursor catches up.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `no such module: vec0` on startup | sqlite-vec extension not loaded | Reinstall the package; `sqlite-vec` is a core dep |
| Inbox files aren't picked up | `CH_INBOX_DIR` unset, wrong subdir, wrong extension | Check `.env`; only `.md` / `.txt` in `meeting/file/email/` |
| Gmail ingest returns 0 documents | Query matches nothing, or label is wrong | Test the query in Gmail's UI; default is `label:context-hub` |
| Upload returns 400 "No extractable text" | Scanned PDF without OCR | Run the PDF through an OCR tool first |
| Upload returns 413 | File > 10 MiB | Split the document, or send the relevant section via `POST /documents` |
| Scheduler doesn't run a source | `SourceConfig.is_enabled=False`, or `INGEST_MODE=mock` in prod | Toggle the config, set `INGEST_MODE=live` |

---

## 8. What Context-Hub is **not**

To save you time:

- **Not a chat interface**: it's a data layer. Connect Claude Desktop or another MCP client for conversation.
- **Not a search engine for the whole machine**: it only knows what you ingest.
- **Not a backup**: deleting the SQLite file loses everything. Back up `data/` if it matters.
- **Not a multi-tenant SaaS**: API keys are per-instance, not per-tenant. Run separate instances for separate trust domains.
