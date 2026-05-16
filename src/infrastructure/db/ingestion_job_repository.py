"""Backward-compatibility shim for PostgresIngestionJobRepository.

The canonical implementation lives in:
    src/adapters/postgres/ingestion_job_repository.py
"""

from src.adapters.postgres.ingestion_job_repository import (  # noqa: F401
    PostgresIngestionJobRepository,
    _domain_to_row,
    _row_to_domain,
)

__all__ = [
    "PostgresIngestionJobRepository",
    "_domain_to_row",
    "_row_to_domain",
]
