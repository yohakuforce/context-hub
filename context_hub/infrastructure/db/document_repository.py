"""Backward-compatibility shim for PostgresDocumentRepository.

The canonical implementation lives in:
    src/adapters/postgres/document_repository.py

This module re-exports everything so that existing imports continue to work
without modification during the transition to the adapter-based layout.
"""

from context_hub.adapters.postgres.document_repository import (  # noqa: F401
    PostgresDocumentRepository,
    _domain_to_values,
    _format_vector,
    _row_to_domain,
)

__all__ = [
    "PostgresDocumentRepository",
    "_domain_to_values",
    "_format_vector",
    "_row_to_domain",
]
