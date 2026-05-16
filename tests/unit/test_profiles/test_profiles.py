"""Tests for src/profiles.py — DI profile registry."""

from __future__ import annotations

import pytest

from src.profiles import (
    BackendProfile,
    PRODUCTION_PROFILE,
    QUICKSTART_PROFILE,
    PERSONAL_PROFILE,
    build_profile,
)


class TestBuildProfile:
    def test_production_profile_returned(self):
        profile = build_profile("production")
        assert profile.name == "production"

    def test_quickstart_profile_returned(self):
        profile = build_profile("quickstart")
        assert profile.name == "quickstart"

    def test_personal_profile_returned(self):
        profile = build_profile("personal")
        assert profile.name == "personal"

    def test_unknown_profile_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown backend profile"):
            build_profile("nonexistent")

    def test_error_message_lists_valid_options(self):
        with pytest.raises(ValueError, match="production"):
            build_profile("typo")


class TestProductionProfile:
    def test_is_backend_profile(self):
        assert isinstance(PRODUCTION_PROFILE, BackendProfile)

    def test_postgres_session_required(self):
        """Postgres factories raise ValueError when session is None."""
        with pytest.raises(ValueError, match="AsyncSession"):
            PRODUCTION_PROFILE.make_project_repo(None)

    def test_document_repo_requires_session(self):
        with pytest.raises(ValueError, match="AsyncSession"):
            PRODUCTION_PROFILE.make_document_repo(None)

    def test_issue_repo_requires_session(self):
        with pytest.raises(ValueError, match="AsyncSession"):
            PRODUCTION_PROFILE.make_issue_repo(None)

    def test_job_repo_requires_session(self):
        with pytest.raises(ValueError, match="AsyncSession"):
            PRODUCTION_PROFILE.make_job_repo(None)


class TestSQLiteProfileStubs:
    """Quickstart / personal profiles raise NotImplementedError until Phase 2."""

    def test_quickstart_project_repo_raises(self):
        with pytest.raises(NotImplementedError, match="SQLite backend"):
            QUICKSTART_PROFILE.make_project_repo(None)

    def test_personal_document_repo_raises(self):
        with pytest.raises(NotImplementedError, match="SQLite backend"):
            PERSONAL_PROFILE.make_document_repo(None)


class TestBackendProfileImmutability:
    def test_frozen_dataclass(self):
        with pytest.raises((AttributeError, TypeError)):
            PRODUCTION_PROFILE.name = "mutated"  # type: ignore[misc]
