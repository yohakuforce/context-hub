"""Profile-aware Settings for Context-Hub.

Three built-in profiles are provided.  The active profile is selected via the
``CH_PROFILE`` environment variable (default: ``quickstart``).

Profile summary (ADR-003):

  quickstart  — sqlite (file) | memory scheduler | mock ingest | ollama (opt) | mock embedding
  personal    — sqlite (file) | sqlite scheduler | mock/live (Slack) | ollama | bge-m3
  production  — postgres      | postgres scheduler | live ingest | claude-code | bge-m3

Each profile defines *default* values for every settings field.  Any field can
be overridden by a corresponding environment variable regardless of which
profile is active.

Usage::

    from src.config.profiles import get_profile_settings
    settings = get_profile_settings()          # reads CH_PROFILE from env
    settings = get_profile_settings("personal")

The ``get_profile_settings()`` result is cached per profile name so repeated
calls within the same process are cheap.
"""

from __future__ import annotations

import functools
import os
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valid profile names (open type for forward compatibility).
ProfileName = Literal["quickstart", "personal", "production"]

_CH_PROFILE_ENV_KEY = "CH_PROFILE"
_DEFAULT_PROFILE: ProfileName = "quickstart"


# ---------------------------------------------------------------------------
# Quickstart profile defaults (zero external dependencies)
# ---------------------------------------------------------------------------


class _QuickstartDefaults:
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "insecure-dev-secret-change-in-production"

    # SQLite file DB for quickstart (persistent across restarts, sharable)
    database_url: str = "sqlite+aiosqlite:///./data/context_hub.db"
    ch_sqlite_db: str = "./data/context_hub.db"

    scheduler_backend: str = "memory"
    ingest_mode: str = "mock"

    # Ollama is optional in quickstart — falls back to mock if unavailable
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Mock embedding: hash-based 1024-dim vectors, zero install cost
    embedding_provider: str = "mock"
    embedding_device: str = "cpu"


# ---------------------------------------------------------------------------
# Personal profile defaults (single-user, no Postgres required)
# ---------------------------------------------------------------------------


class _PersonalDefaults:
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "insecure-dev-secret-change-in-production"

    database_url: str = "sqlite+aiosqlite:///./data/context_hub.db"
    ch_sqlite_db: str = "./data/context_hub.db"

    scheduler_backend: str = "sqlite"
    ingest_mode: str = "mock"

    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    embedding_provider: str = "bge-m3"
    embedding_device: str = "cpu"


# ---------------------------------------------------------------------------
# Production profile defaults (full feature set, Postgres required)
# ---------------------------------------------------------------------------


class _ProductionDefaults:
    app_env: str = "production"
    log_level: str = "WARNING"
    secret_key: str = ""  # Must be overridden via env var

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/context_hub"
    ch_sqlite_db: str = ""  # Not used in production

    scheduler_backend: str = "postgres"
    ingest_mode: str = "live"

    llm_provider: str = "claude-code"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    embedding_provider: str = "bge-m3"
    embedding_device: str = "cpu"


# ---------------------------------------------------------------------------
# Unified ProfileSettings
# ---------------------------------------------------------------------------


class ProfileSettings(BaseSettings):
    """Pydantic BaseSettings with profile-aware defaults.

    Default values are set by the active profile (``CH_PROFILE`` env var).
    Any field can be overridden by the corresponding environment variable
    regardless of which profile is active.

    Environment variables are case-insensitive.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_env: str = _QuickstartDefaults.app_env
    log_level: str = _QuickstartDefaults.log_level
    secret_key: str = Field(default=_QuickstartDefaults.secret_key)

    # --- Database ---
    database_url: str = Field(default=_QuickstartDefaults.database_url)
    ch_sqlite_db: str = _QuickstartDefaults.ch_sqlite_db

    # --- Scheduler ---
    # Values: memory | sqlite | postgres
    scheduler_backend: str = _QuickstartDefaults.scheduler_backend
    scheduler_sqlite_db: str = "./data/scheduler.db"

    # --- Ingest ---
    # Values: mock | live
    ingest_mode: str = _QuickstartDefaults.ingest_mode

    # --- LLM Provider ---
    # Values: claude-code | codex | ollama | mock
    llm_provider: str = _QuickstartDefaults.llm_provider
    claude_code_timeout_seconds: float = 120.0
    codex_timeout_seconds: float = 120.0
    ollama_base_url: str = _QuickstartDefaults.ollama_base_url
    ollama_model: str = _QuickstartDefaults.ollama_model

    # --- Embedding Provider ---
    # Values: bge-m3 | mock
    embedding_provider: str = _QuickstartDefaults.embedding_provider
    embedding_device: str = _QuickstartDefaults.embedding_device

    # --- Slack ---
    slack_bot_token: str | None = None

    # --- Backlog ---
    backlog_api_key: str | None = None
    backlog_space_key: str | None = None

    # --- Redmine ---
    redmine_api_key: str | None = None
    redmine_base_url: str | None = None

    # --- Whisper ---
    whisper_model: str = "medium"

    # --- Data paths ---
    meetings_data_dir: str = "/app/data/meetings"
    documents_data_dir: str = "/app/data/documents"


def _build_profile_overrides(profile: ProfileName) -> dict[str, str]:
    """Return a dict of field overrides for *profile*.

    All values are coerced to strings so they can be safely injected into the
    process environment and picked up by Pydantic BaseSettings at a higher
    priority than constructor defaults.

    Args:
        profile: One of "quickstart", "personal", "production".

    Returns:
        Dict of field name (upper-case) -> string value for the given profile.
    """
    _src_map: dict[str, type] = {
        "quickstart": _QuickstartDefaults,
        "personal": _PersonalDefaults,
        "production": _ProductionDefaults,
    }
    src = _src_map[profile]
    return {
        field.upper(): str(getattr(src, field))
        for field in vars(src)
        if not field.startswith("_") and getattr(src, field) != ""
    }


@functools.lru_cache(maxsize=4)
def get_profile_settings(profile: ProfileName | None = None) -> ProfileSettings:
    """Return a ProfileSettings instance for the given *profile*.

    Result is cached per profile name so repeated calls are cheap.

    Args:
        profile: One of "quickstart", "personal", "production", or None to
                 read the ``CH_PROFILE`` environment variable (default:
                 "quickstart").

    Returns:
        ProfileSettings instance with profile-appropriate default values.

    Raises:
        ValueError: If *profile* is not a recognised profile name.
    """
    resolved: ProfileName = profile or _resolve_env_profile()
    _validate_profile_name(resolved)
    overrides = _build_profile_overrides(resolved)

    # Inject profile defaults into the environment so that Pydantic BaseSettings
    # reads them at higher priority than field defaults.  Existing env vars win
    # because setdefault does not overwrite already-set keys.
    import os as _os
    env_backup: dict[str, str] = {}
    for key, value in overrides.items():
        if key not in _os.environ:
            _os.environ[key] = value
            env_backup[key] = value
    try:
        return ProfileSettings()
    finally:
        for key in env_backup:
            _os.environ.pop(key, None)


def _resolve_env_profile() -> ProfileName:
    """Read CH_PROFILE from the environment.

    Returns:
        Profile name string, defaulting to "quickstart".
    """
    raw = os.environ.get(_CH_PROFILE_ENV_KEY, _DEFAULT_PROFILE)
    return raw  # type: ignore[return-value]  # validated downstream


def _validate_profile_name(name: str) -> None:
    """Raise ValueError for unrecognised profile names.

    Args:
        name: Profile name to validate.

    Raises:
        ValueError: If *name* is not one of the built-in profiles.
    """
    valid = {"quickstart", "personal", "production"}
    if name not in valid:
        raise ValueError(
            f"Unknown profile {name!r}. Valid options: {', '.join(sorted(valid))}"
        )
