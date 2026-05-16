"""Unit tests for src/config/profiles.py — Settings 3-layer profile system.

Verifies:
- get_profile_settings() returns correct defaults per profile.
- CH_PROFILE env var is respected.
- Unknown profiles raise ValueError.
- Environment variable overrides work across all profiles.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_settings(profile: str, extra_env: dict[str, str] | None = None):
    """Return a fresh ProfileSettings instance, bypassing lru_cache.

    extra_env values take precedence over profile defaults because they are
    applied to the process environment, which Pydantic BaseSettings reads at
    a higher priority than constructor keyword arguments.
    """
    from src.config.profiles import ProfileSettings, _build_profile_overrides

    # _build_profile_overrides now returns UPPER_CASE keys
    overrides = _build_profile_overrides(profile)  # type: ignore[arg-type]
    # extra_env overrides are merged last so they win over profile defaults
    merged_env = {**overrides, **{k.upper(): v for k, v in (extra_env or {}).items()}}
    with patch.dict(os.environ, merged_env, clear=False):
        return ProfileSettings()


# ---------------------------------------------------------------------------
# Quickstart profile
# ---------------------------------------------------------------------------


class TestQuickstartProfile:
    def test_scheduler_backend_is_memory(self) -> None:
        s = _fresh_settings("quickstart")
        assert s.scheduler_backend == "memory"

    def test_embedding_provider_is_mock(self) -> None:
        s = _fresh_settings("quickstart")
        assert s.embedding_provider == "mock"

    def test_ingest_mode_is_mock(self) -> None:
        s = _fresh_settings("quickstart")
        assert s.ingest_mode == "mock"

    def test_llm_provider_is_ollama(self) -> None:
        s = _fresh_settings("quickstart")
        assert s.llm_provider == "ollama"

    def test_database_url_is_sqlite(self) -> None:
        s = _fresh_settings("quickstart")
        assert "sqlite" in s.database_url

    def test_app_env_is_development(self) -> None:
        s = _fresh_settings("quickstart")
        assert s.app_env == "development"


# ---------------------------------------------------------------------------
# Personal profile
# ---------------------------------------------------------------------------


class TestPersonalProfile:
    def test_scheduler_backend_is_sqlite(self) -> None:
        s = _fresh_settings("personal")
        assert s.scheduler_backend == "sqlite"

    def test_embedding_provider_is_bge_m3(self) -> None:
        s = _fresh_settings("personal")
        assert s.embedding_provider == "bge-m3"

    def test_ingest_mode_is_mock(self) -> None:
        s = _fresh_settings("personal")
        assert s.ingest_mode == "mock"

    def test_llm_provider_is_ollama(self) -> None:
        s = _fresh_settings("personal")
        assert s.llm_provider == "ollama"

    def test_database_url_is_sqlite(self) -> None:
        s = _fresh_settings("personal")
        assert "sqlite" in s.database_url


# ---------------------------------------------------------------------------
# Production profile
# ---------------------------------------------------------------------------


class TestProductionProfile:
    def test_scheduler_backend_is_postgres(self) -> None:
        s = _fresh_settings("production")
        assert s.scheduler_backend == "postgres"

    def test_embedding_provider_is_bge_m3(self) -> None:
        s = _fresh_settings("production")
        assert s.embedding_provider == "bge-m3"

    def test_ingest_mode_is_live(self) -> None:
        s = _fresh_settings("production")
        assert s.ingest_mode == "live"

    def test_llm_provider_is_claude_code(self) -> None:
        s = _fresh_settings("production")
        assert s.llm_provider == "claude-code"

    def test_database_url_is_postgres(self) -> None:
        s = _fresh_settings("production")
        assert "postgresql" in s.database_url

    def test_app_env_is_production(self) -> None:
        s = _fresh_settings("production")
        assert s.app_env == "production"

    def test_log_level_is_warning(self) -> None:
        s = _fresh_settings("production")
        assert s.log_level == "WARNING"


# ---------------------------------------------------------------------------
# get_profile_settings factory
# ---------------------------------------------------------------------------


class TestGetProfileSettings:
    def test_unknown_profile_raises(self) -> None:
        from src.config.profiles import _validate_profile_name

        with pytest.raises(ValueError, match="Unknown profile"):
            _validate_profile_name("staging")

    def test_ch_profile_env_var_resolves(self) -> None:
        from src.config.profiles import _resolve_env_profile

        with patch.dict(os.environ, {"CH_PROFILE": "personal"}):
            resolved = _resolve_env_profile()
        assert resolved == "personal"

    def test_ch_profile_defaults_to_quickstart(self) -> None:
        from src.config.profiles import _resolve_env_profile

        env = os.environ.copy()
        env.pop("CH_PROFILE", None)
        with patch.dict(os.environ, env, clear=True):
            resolved = _resolve_env_profile()
        assert resolved == "quickstart"

    def test_env_var_override_in_quickstart(self) -> None:
        """EMBEDDING_PROVIDER env var should override quickstart default."""
        s = _fresh_settings("quickstart", extra_env={"EMBEDDING_PROVIDER": "bge-m3"})
        assert s.embedding_provider == "bge-m3"

    def test_env_var_override_in_production(self) -> None:
        """LLM_PROVIDER env var should override production default."""
        s = _fresh_settings("production", extra_env={"LLM_PROVIDER": "ollama"})
        assert s.llm_provider == "ollama"


# ---------------------------------------------------------------------------
# Profile overrides are distinct
# ---------------------------------------------------------------------------


class TestProfileDistinctness:
    def test_quickstart_and_personal_differ_in_scheduler(self) -> None:
        qs = _fresh_settings("quickstart")
        ps = _fresh_settings("personal")
        assert qs.scheduler_backend != ps.scheduler_backend

    def test_quickstart_and_production_differ_in_db(self) -> None:
        qs = _fresh_settings("quickstart")
        prod = _fresh_settings("production")
        assert qs.database_url != prod.database_url

    def test_quickstart_and_production_differ_in_llm(self) -> None:
        qs = _fresh_settings("quickstart")
        prod = _fresh_settings("production")
        assert qs.llm_provider != prod.llm_provider
