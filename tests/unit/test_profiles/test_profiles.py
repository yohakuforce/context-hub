"""Tests for src/profiles.py — DI profile registry."""

from __future__ import annotations

import pytest

from context_hub.profiles import (
    BackendProfile,
    PRODUCTION_PROFILE,
    QUICKSTART_PROFILE,
    PERSONAL_PROFILE,
    build_profile,
)


class TestBuildProfile:
    def test_production_profile_returned(self) -> None:
        profile = build_profile("production")
        assert profile.name == "production"

    def test_quickstart_profile_returned(self) -> None:
        profile = build_profile("quickstart")
        assert profile.name == "quickstart"

    def test_personal_profile_returned(self) -> None:
        profile = build_profile("personal")
        assert profile.name == "personal"

    def test_unknown_profile_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend profile"):
            build_profile("nonexistent")

    def test_error_message_lists_valid_options(self) -> None:
        with pytest.raises(ValueError, match="production"):
            build_profile("typo")


class TestProductionProfile:
    def test_is_backend_profile(self) -> None:
        assert isinstance(PRODUCTION_PROFILE, BackendProfile)

    def test_postgres_session_required(self) -> None:
        """Postgres factories raise ValueError when session is None."""
        with pytest.raises(ValueError, match="AsyncSession"):
            PRODUCTION_PROFILE.make_project_repo(None)

    def test_document_repo_requires_session(self) -> None:
        with pytest.raises(ValueError, match="AsyncSession"):
            PRODUCTION_PROFILE.make_document_repo(None)

    def test_issue_repo_requires_session(self) -> None:
        with pytest.raises(ValueError, match="AsyncSession"):
            PRODUCTION_PROFILE.make_issue_repo(None)

    def test_job_repo_requires_session(self) -> None:
        with pytest.raises(ValueError, match="AsyncSession"):
            PRODUCTION_PROFILE.make_job_repo(None)


class TestSQLiteProfiles:
    """Quickstart / personal profiles now return SQLite repositories (Phase 2)."""

    def test_quickstart_project_repo_returns_repo(self) -> None:
        from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
        repo = QUICKSTART_PROFILE.make_project_repo(None)
        assert isinstance(repo, SqliteProjectRepository)

    def test_quickstart_document_repo_returns_repo(self) -> None:
        from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
        repo = QUICKSTART_PROFILE.make_document_repo(None)
        assert isinstance(repo, SqliteDocumentRepository)

    def test_quickstart_issue_repo_returns_repo(self) -> None:
        from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
        repo = QUICKSTART_PROFILE.make_issue_repo(None)
        assert isinstance(repo, SqliteIssueRepository)

    def test_quickstart_job_repo_returns_repo(self) -> None:
        from context_hub.adapters.sqlite.ingestion_job_repository import SqliteIngestionJobRepository
        repo = QUICKSTART_PROFILE.make_job_repo(None)
        assert isinstance(repo, SqliteIngestionJobRepository)

    def test_personal_project_repo_returns_repo(self) -> None:
        from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
        repo = PERSONAL_PROFILE.make_project_repo(None)
        assert isinstance(repo, SqliteProjectRepository)

    def test_personal_document_repo_returns_repo(self) -> None:
        from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
        repo = PERSONAL_PROFILE.make_document_repo(None)
        assert isinstance(repo, SqliteDocumentRepository)


class TestBackendProfileImmutability:
    def test_frozen_dataclass(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            PRODUCTION_PROFILE.name = "mutated"  # type: ignore[misc]
