"""Backward-compatibility shim for PostgresIssueRepository.

The canonical implementation lives in:
    src/adapters/postgres/issue_repository.py
"""

from src.adapters.postgres.issue_repository import (  # noqa: F401
    PostgresIssueRepository,
    _domain_to_values,
    _row_to_domain,
)

__all__ = [
    "PostgresIssueRepository",
    "_domain_to_values",
    "_row_to_domain",
]
