"""SQLite adapter package for Context-Hub.

Provides VectorStore, FullTextSearch, MigrationRunner, and Repository
implementations backed by SQLite + sqlite-vec + FTS5.

Designed for single-user local deployments (quickstart / personal profiles).
"""

from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
from context_hub.adapters.sqlite.fts_search import SqliteFts5Search
from context_hub.adapters.sqlite.ingestion_job_repository import SqliteIngestionJobRepository
from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
from context_hub.adapters.sqlite.migration_runner import SqliteMigrationRunner
from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
from context_hub.adapters.sqlite.vec_store import SqliteVecStore

__all__ = [
    "SqliteDocumentRepository",
    "SqliteFts5Search",
    "SqliteIngestionJobRepository",
    "SqliteIssueRepository",
    "SqliteMigrationRunner",
    "SqliteProjectRepository",
    "SqliteVecStore",
]
