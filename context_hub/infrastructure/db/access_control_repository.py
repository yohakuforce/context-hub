"""Backward-compatibility shim for Postgres access-control repositories.

The canonical implementation lives in:
    src/adapters/postgres/access_control_repository.py
"""

from context_hub.adapters.postgres.access_control_repository import (  # noqa: F401
    PostgresConsumerRepository,
    PostgresPermissionRepository,
    _consumer_domain_to_row,
    _consumer_row_to_domain,
    _permission_domain_to_row,
    _permission_row_to_domain,
)

__all__ = [
    "PostgresConsumerRepository",
    "PostgresPermissionRepository",
    "_consumer_domain_to_row",
    "_consumer_row_to_domain",
    "_permission_domain_to_row",
    "_permission_row_to_domain",
]
