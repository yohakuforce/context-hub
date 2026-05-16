"""Unit tests for src/adapters/scheduler/postgres_store._normalise_url.

Covers M-3: postgres:// and postgresql:// schemes must be converted to
postgresql+psycopg2://.
"""

from __future__ import annotations

from context_hub.adapters.scheduler.postgres_store import _normalise_url


class TestNormaliseUrl:
    """M-3: _normalise_url handles all expected input schemes."""

    def test_asyncpg_converted_to_psycopg2(self) -> None:
        url = "postgresql+asyncpg://user:pass@host:5432/db"
        assert _normalise_url(url) == "postgresql+psycopg2://user:pass@host:5432/db"

    def test_postgres_shorthand_converted(self) -> None:
        """Heroku/Render default postgres:// scheme must be accepted."""
        url = "postgres://user:pass@host:5432/db"
        assert _normalise_url(url) == "postgresql+psycopg2://user:pass@host:5432/db"

    def test_bare_postgresql_converted(self) -> None:
        """postgresql:// without driver suffix must be normalised."""
        url = "postgresql://user:pass@host:5432/db"
        assert _normalise_url(url) == "postgresql+psycopg2://user:pass@host:5432/db"

    def test_psycopg2_url_unchanged(self) -> None:
        """Already-correct URLs must pass through untouched."""
        url = "postgresql+psycopg2://user:pass@host:5432/db"
        assert _normalise_url(url) == url

    def test_sqlite_url_unchanged(self) -> None:
        """Non-postgres URLs must be returned as-is (not relevant but safe)."""
        url = "sqlite:///./data/scheduler.db"
        assert _normalise_url(url) == url

    def test_only_first_occurrence_replaced(self) -> None:
        """Only the scheme prefix is replaced, not any later occurrence."""
        url = "postgres://user:postgres@host:5432/db"
        result = _normalise_url(url)
        assert result.startswith("postgresql+psycopg2://")
        # The password 'postgres' inside the URL must remain intact
        assert "user:postgres@" in result
