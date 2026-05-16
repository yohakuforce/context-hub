"""SQLite adapter package for Context-Hub.

Provides VectorStore, FullTextSearch, MigrationRunner, and Repository
implementations backed by SQLite + sqlite-vec + FTS5.

Designed for single-user local deployments (quickstart / personal profiles).
"""

from src.adapters.sqlite.document_repository import SqliteDocumentRepository
from src.adapters.sqlite.fts_search import SqliteFts5Search
from src.adapters.sqlite.ingestion_job_repository import SqliteIngestionJobRepository
from src.adapters.sqlite.issue_repository import SqliteIssueRepository
from src.adapters.sqlite.migration_runner import SqliteMigrationRunner
from src.adapters.sqlite.project_repository import SqliteProjectRepository
from src.adapters.sqlite.vec_store import SqliteVecStore

__all__ = [
    "SqliteDocumentRepository",
    "SqliteFts5Search",
    "SqliteIngestionJobRepository",
    "SqliteIssueRepository",
    "SqliteMigrationRunner",
    "SqliteProjectRepository",
    "SqliteVecStore",
]
