# Context-Hub Architecture

This document summarises the Architecture Decision Records (ADR-001 through ADR-005)
that govern the design of Context-Hub.

---

## ADR-001: Domain Model

**Decision**: Use a clean domain model with `Project`, `Document`, `IngestionJob`, and `Issue`
as the core entities.

**Rationale**: Separating domain logic from infrastructure allows the storage backend
(SQLite vs PostgreSQL) to be swapped without touching business logic.

**Key types** (see `context_hub/domain/`, `context_hub/shared/types.py`):

- `ProjectId` — `NewType(str, UUID)` wrapper, prevents mixing raw strings
- `Document` — immutable dataclass with content, embedding vector, source metadata
- `IngestionJob` — tracks sync state per project/source pair
- `Issue` — normalised representation of Backlog/Redmine issues

---

## ADR-002: Repository Pattern

**Decision**: All data access goes through Protocol-based repository interfaces.

**Rationale**:
- Business logic depends on abstract interfaces, not SQLAlchemy or raw SQL
- Easy to mock in tests (no database required for unit tests)
- Enables the quickstart SQLite adapter and production PostgreSQL adapter to be swapped

**Interfaces** (see `context_hub/core/`):

- `DocumentRepository` — `find_by_id`, `find_all`, `save`, `delete`
- `ProjectRepository` — same CRUD set
- `IngestionJobRepository` — `find_by_project_source`, `save`
- `VectorStore` — `upsert`, `search`, `delete`
- `FTSStore` — `index`, `search`

---

## ADR-003: Three-Profile Settings

**Decision**: Provide three named profiles (`quickstart`, `personal`, `production`)
via pydantic-settings with `CH_PROFILE` environment variable selection.

**Rationale**: Most projects need different defaults for development vs production.
Hard-coding production credentials as defaults is a security risk.

| Profile | Database | Embedding | Scheduler |
|---|---|---|---|
| `quickstart` | SQLite | mock (hash) | memory |
| `personal` | SQLite | BGE-M3 | SQLite |
| `production` | PostgreSQL | BGE-M3 | PostgreSQL |

Any field can be overridden by environment variable regardless of which profile is active.

---

## ADR-004: Hybrid Search with RRF Fusion

**Decision**: Combine vector similarity search (sqlite-vec / pgvector) with FTS5 keyword
search using Reciprocal Rank Fusion (RRF) to merge result sets.

**Rationale**: Vector search excels at semantic similarity but misses exact keyword matches.
FTS5 handles exact matches but has no semantic understanding. RRF (k=60) is a simple,
parameter-free fusion method that works well in practice.

**Implementation** (see `context_hub/services/hybrid.py`):
- Both backends produce a ranked list of `(document_id, score)` pairs
- RRF formula: `score(d) = sum(1 / (k + rank(d)))` across backends
- Merged result is re-ranked by RRF score and truncated to `top_k`

---

## ADR-005: MCP as First-Class Entry Point

**Decision**: The MCP server is a first-class entry point, equal in status to the HTTP REST API.
Both are thin adapters over the shared `QueryService`.

**Rationale**:
- AI agents (Claude Desktop, Claude Code) consume context via MCP, not HTTP
- Making MCP a second-class citizen (delegating to HTTP internally) adds latency and complexity
- Shared `QueryService` ensures identical query semantics across both transports

**Architecture**:

```
Claude Desktop / Claude Code
         |
         | stdio (JSON-RPC 2.0)
         v
   context_hub/mcp/server.py          <-- thin MCP adapter
         |
         | calls
         v
   context_hub/application/           <-- shared QueryService, IngestionService
   query_service.py
         |
         | depends on
         v
   context_hub/core/ (Protocols)      <-- VectorStore, FTSStore, SchedulerStore
         |
         v
   SQLite / PostgreSQL
```

**MCP Protocol Version**: `2024-11-05` (exported as `MCP_PROTOCOL_VERSION` from `context_hub/mcp/__init__.py`)

**HTTP compatibility check**: `GET /mcp/version` returns the protocol version so AI-PM
can verify compatibility at startup without opening the stdio channel.

**CLI flags**:
- `context-hub serve` — both HTTP + MCP (default)
- `context-hub serve --mcp-only` — MCP stdio only, no HTTP
- `context-hub serve --http-only` — HTTP only, no MCP

---

## Component Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                      Context-Hub Process                       │
│                                                                │
│  ┌─────────────────┐        ┌───────────────────────────────┐  │
│  │  MCP Server     │        │  FastAPI (HTTP REST)          │  │
│  │  stdio JSON-RPC │        │  /api/v1/{projects,query,...} │  │
│  │  context_hub/mcp/       │        │  context_hub/api/                     │  │
│  └────────┬────────┘        └──────────────┬────────────────┘  │
│           │                                │                   │
│           └───────────────┬────────────────┘                   │
│                           ▼                                    │
│              context_hub/application/query_service.py                  │
│              context_hub/application/ingestion_service.py              │
│                           │                                    │
│           ┌───────────────┼────────────────┐                   │
│           ▼               ▼                ▼                   │
│   VectorStore          FTSStore      SchedulerStore            │
│   (Protocol)          (Protocol)      (Protocol)               │
│           │               │                │                   │
│    ┌──────┴──┐     ┌──────┴──┐    ┌────────┴───────┐          │
│    │ sqlite- │     │  FTS5   │    │ memory/sqlite/ │          │
│    │  vec    │     │         │    │ postgres       │          │
│    │ pgvector│     │ pg FTS  │    │ APScheduler    │          │
│    └─────────┘     └─────────┘    └────────────────┘          │
└────────────────────────────────────────────────────────────────┘
```
