"""Project aggregate root and related value objects.

Project is the top-level bounded context boundary that all Documents and Issues
belong to. It also holds the SourceConfig list that defines which data sources
are active for this project.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from context_hub.shared.types import ProjectId, SourceType, new_id


@dataclass(frozen=True)
class EncryptedCredentials:
    """Holds an encrypted API key for a Source.

    The plaintext key is never stored on this object — only the encrypted form
    plus metadata needed for decryption (algorithm / encrypted_at).
    On personal dev machines this holds a placeholder until the real key is
    provided on the company PC.
    """

    encrypted_value: str
    algorithm: str
    encrypted_at: datetime


@dataclass(frozen=True)
class SourceConfig:
    """Configuration for a single data source within a Project.

    Immutable value object — any change produces a new instance.
    """

    source_type: SourceType
    sync_interval_minutes: int
    is_enabled: bool
    credentials: EncryptedCredentials | None = None
    # Slack-specific: list of channel IDs to watch
    channel_ids: tuple[str, ...] = field(default_factory=tuple)
    # Backlog-specific: project key (e.g. "MYPROJ")
    backlog_project_key: str | None = None
    # Redmine-specific: project identifier slug
    redmine_project_identifier: str | None = None

    def with_enabled(self, is_enabled: bool) -> "SourceConfig":
        """Return a new SourceConfig with is_enabled changed."""
        return replace(self, is_enabled=is_enabled)


@dataclass
class Project:
    """Aggregate root for a Context-Hub project.

    Maps 1:1 to a project in AI-Project-Manager via external_project_id.
    Mutable — individual fields are updated via factory methods that return
    new instances (immutable-update pattern).
    """

    id: ProjectId
    name: str
    external_project_id: str | None
    sources: list[SourceConfig]
    created_at: datetime
    updated_at: datetime

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        name: str,
        external_project_id: str | None = None,
        sources: list[SourceConfig] | None = None,
    ) -> "Project":
        now = datetime.utcnow()
        return cls(
            id=ProjectId(new_id()),
            name=name,
            external_project_id=external_project_id,
            sources=sources or [],
            created_at=now,
            updated_at=now,
        )

    # ------------------------------------------------------------------
    # Domain behaviour
    # ------------------------------------------------------------------

    def add_source(self, config: SourceConfig) -> "Project":
        """Return a new Project with the given source added.

        Raises ValueError if a config for the same SourceType already exists.
        """
        for existing in self.sources:
            if existing.source_type == config.source_type:
                raise ValueError(
                    f"Source type {config.source_type} is already configured "
                    f"for project '{self.name}'. Remove it first."
                )
        return Project(
            id=self.id,
            name=self.name,
            external_project_id=self.external_project_id,
            sources=[*self.sources, config],
            created_at=self.created_at,
            updated_at=datetime.utcnow(),
        )

    def remove_source(self, source_type: SourceType) -> "Project":
        """Return a new Project with the given source removed."""
        return Project(
            id=self.id,
            name=self.name,
            external_project_id=self.external_project_id,
            sources=[s for s in self.sources if s.source_type != source_type],
            created_at=self.created_at,
            updated_at=datetime.utcnow(),
        )

    def get_source(self, source_type: SourceType) -> SourceConfig | None:
        """Return the SourceConfig for the given type, or None."""
        for source in self.sources:
            if source.source_type == source_type:
                return source
        return None

    def active_sources(self) -> list[SourceConfig]:
        """Return only enabled source configs."""
        return [s for s in self.sources if s.is_enabled]
