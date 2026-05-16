"""Backward-compatibility shim for PostgresProjectRepository.

The canonical implementation lives in:
    src/adapters/postgres/project_repository.py
"""

from context_hub.adapters.postgres.project_repository import (  # noqa: F401
    PostgresProjectRepository,
    _domain_to_row,
    _sources_to_json,
    _row_to_domain,
    _json_to_source,
)

__all__ = [
    "PostgresProjectRepository",
    "_domain_to_row",
    "_sources_to_json",
    "_row_to_domain",
    "_json_to_source",
]
