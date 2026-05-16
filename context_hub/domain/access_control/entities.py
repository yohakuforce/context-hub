"""Access Control bounded context — Consumer and Permission aggregates.

API keys are stored as bcrypt hashes — never in plaintext.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from context_hub.shared.types import ConsumerId, PermissionId, ProjectId, Scope, new_id


@dataclass(frozen=True)
class HashedApiKey:
    """Stores a bcrypt hash of the API key plus provenance metadata.

    The plaintext key is only available at generation time; after that
    only the hash is kept.
    """

    hash_value: str        # bcrypt hash
    algorithm: str = "bcrypt"
    created_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.utcnow())


@dataclass
class Consumer:
    """Aggregate root for an API consumer (AI-Project-Manager, SF-AI-Foundation, etc.).

    API key generation is the responsibility of the application service layer
    (hashing is done there before constructing this entity).
    """

    id: ConsumerId
    name: str
    hashed_api_key: HashedApiKey
    is_active: bool
    created_at: datetime

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, name: str, hashed_api_key: HashedApiKey) -> "Consumer":
        return cls(
            id=ConsumerId(new_id()),
            name=name,
            hashed_api_key=hashed_api_key,
            is_active=True,
            created_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def deactivate(self) -> "Consumer":
        return Consumer(
            id=self.id,
            name=self.name,
            hashed_api_key=self.hashed_api_key,
            is_active=False,
            created_at=self.created_at,
        )


@dataclass(frozen=True)
class Permission:
    """Maps a Consumer to a set of Scopes on a Project (or all projects).

    If project_id is None the permission applies to ALL projects.
    """

    id: PermissionId
    consumer_id: ConsumerId
    project_id: Optional[ProjectId]  # None = global
    scopes: frozenset[Scope]
    created_at: datetime

    @classmethod
    def create(
        cls,
        consumer_id: ConsumerId,
        scopes: set[Scope],
        project_id: Optional[ProjectId] = None,
    ) -> "Permission":
        return cls(
            id=PermissionId(new_id()),
            consumer_id=consumer_id,
            project_id=project_id,
            scopes=frozenset(scopes),
            created_at=datetime.utcnow(),
        )

    def has_scope(self, scope: Scope) -> bool:
        return scope in self.scopes or Scope.ADMIN in self.scopes

    def covers_project(self, project_id: ProjectId) -> bool:
        """True if this permission applies to the given project."""
        return self.project_id is None or self.project_id == project_id
