-- Context-Hub SQLite schema — revision 001
-- Designed for single-user local deployments (quickstart / personal profiles).
--
-- Vector storage: sqlite-vec virtual table (requires the extension to be loaded
--   before this migration runs via sqlite_vec.load(conn)).
-- Full-text search: FTS5 virtual table with unicode61 tokenizer and trigram
--   support for CJK languages (Japanese, Chinese, Korean).
-- WAL mode: enabled at the connection level before migration for performance.
--
-- IMPORTANT: WAL journal mode must be set before creating any tables.
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ---------------------------------------------------------------------------
-- Projects
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,          -- UUID string
    name        TEXT NOT NULL,
    external_project_id TEXT,
    sources     TEXT NOT NULL DEFAULT '[]', -- JSON array of SourceConfig
    created_at  TEXT NOT NULL,              -- ISO-8601
    updated_at  TEXT NOT NULL               -- ISO-8601
);

CREATE INDEX IF NOT EXISTS ix_projects_external_id
    ON projects (external_project_id);

-- ---------------------------------------------------------------------------
-- IngestionJobs (declared before Documents due to FK dependency)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id                       TEXT PRIMARY KEY,
    project_id               TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    source_type              TEXT NOT NULL,
    status                   TEXT NOT NULL,
    sync_cursor_source_type  TEXT,
    sync_cursor_value        TEXT,
    items_processed          INTEGER NOT NULL DEFAULT 0,
    errors                   TEXT NOT NULL DEFAULT '[]', -- JSON array
    started_at               TEXT,
    finished_at              TEXT,
    created_at               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_project_id
    ON ingestion_jobs (project_id);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_status
    ON ingestion_jobs (status);

-- ---------------------------------------------------------------------------
-- Documents
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    source_type     TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    source_url      TEXT,
    author_id       TEXT,
    raw_created_at  TEXT,
    summary         TEXT,
    language        TEXT,
    tags            TEXT DEFAULT '[]',     -- JSON array of strings
    entities        TEXT DEFAULT '[]',     -- JSON array of {name, entity_type}
    embedding_model TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}', -- JSON object
    ingestion_job_id TEXT REFERENCES ingestion_jobs (id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (project_id, source_type, external_id)
);

CREATE INDEX IF NOT EXISTS ix_documents_project_id
    ON documents (project_id);
CREATE INDEX IF NOT EXISTS ix_documents_ingestion_job_id
    ON documents (ingestion_job_id);

-- ---------------------------------------------------------------------------
-- Issues
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS issues (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    source_type     TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL,
    priority        TEXT NOT NULL,
    assignee_external_id TEXT,
    assignee_name   TEXT,
    due_date        TEXT,
    labels          TEXT NOT NULL DEFAULT '[]', -- JSON array
    comments        TEXT NOT NULL DEFAULT '[]', -- JSON array
    embedding_model TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (project_id, source_type, external_id)
);

CREATE INDEX IF NOT EXISTS ix_issues_project_id
    ON issues (project_id);

-- ---------------------------------------------------------------------------
-- Consumers (API key holders)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS consumers (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    api_key_hash        TEXT NOT NULL,
    api_key_algorithm   TEXT NOT NULL DEFAULT 'bcrypt',
    api_key_created_at  TEXT NOT NULL,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Permissions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS permissions (
    id          TEXT PRIMARY KEY,
    consumer_id TEXT NOT NULL REFERENCES consumers (id) ON DELETE CASCADE,
    project_id  TEXT REFERENCES projects (id) ON DELETE CASCADE,
    scopes      TEXT NOT NULL DEFAULT '[]', -- JSON array
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_permissions_consumer_id
    ON permissions (consumer_id);
CREATE INDEX IF NOT EXISTS ix_permissions_project_id
    ON permissions (project_id);

-- ---------------------------------------------------------------------------
-- Audit Logs (append-only)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_logs (
    id              TEXT PRIMARY KEY,
    operation_type  TEXT NOT NULL,
    consumer_id     TEXT,
    project_id      TEXT,
    resource_id     TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}',
    occurred_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_operation_type
    ON audit_logs (operation_type);
CREATE INDEX IF NOT EXISTS ix_audit_logs_occurred_at
    ON audit_logs (occurred_at);

-- ---------------------------------------------------------------------------
-- Vector virtual table (sqlite-vec)
-- Stores 1024-dim float32 embeddings (BGE-M3 compatible with Postgres backend).
-- NOTE: The sqlite-vec extension MUST be loaded before this statement.
-- ---------------------------------------------------------------------------

CREATE VIRTUAL TABLE IF NOT EXISTS document_embeddings USING vec0 (
    doc_id TEXT PRIMARY KEY,
    embedding FLOAT[1024]
);

-- ---------------------------------------------------------------------------
-- FTS5 virtual table for full-text search.
-- Uses the trigram tokenizer which provides character-level n-gram indexing.
-- Trigram supports both Latin scripts (via substring matching) and CJK languages
-- (Japanese, Chinese, Korean) without requiring a language-specific tokenizer.
-- Trade-off: index size is larger than unicode61, but recall is uniformly high.
-- ---------------------------------------------------------------------------

CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5 (
    doc_id UNINDEXED,
    content,
    project_id UNINDEXED,
    tokenize = "trigram"
);

-- ---------------------------------------------------------------------------
-- Schema version tracking (lightweight, no Alembic)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS schema_migrations (
    revision    TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL
);
