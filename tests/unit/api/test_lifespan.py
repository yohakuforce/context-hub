"""Unit tests for FastAPI lifespan — scheduler startup and shutdown.

Ensures:
- SCHEDULER_BACKEND=memory is the default and prevents side effects.
- The lifespan context manager starts and stops the scheduler cleanly.
- TestClient triggers the lifespan context manager correctly.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestLifespanWithMemoryBackend:
    """lifespan tests using SCHEDULER_BACKEND=memory to avoid FS side effects."""

    def test_app_starts_and_health_returns_200(self) -> None:
        """App must start (lifespan must not raise) and respond to /health."""
        with patch.dict(os.environ, {"SCHEDULER_BACKEND": "memory"}):
            from context_hub.main import create_app

            test_app = create_app()
            with TestClient(test_app) as client:
                response = client.get("/health")
        assert response.status_code == 200

    def test_health_json_has_status_ok(self) -> None:
        """Health endpoint must return {"status": "ok"} during lifespan."""
        with patch.dict(os.environ, {"SCHEDULER_BACKEND": "memory"}):
            from context_hub.main import create_app

            test_app = create_app()
            with TestClient(test_app) as client:
                data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_lifespan_startup_does_not_require_postgres(self) -> None:
        """Quickstart mode must work without a Postgres connection."""
        env_overrides = {
            "SCHEDULER_BACKEND": "memory",
            "DATABASE_URL": "sqlite+aiosqlite:///./data/context_hub.db",
        }
        with patch.dict(os.environ, env_overrides):
            from context_hub.main import create_app

            test_app = create_app()
            # If lifespan raises, TestClient.__enter__ will propagate the error.
            with TestClient(test_app) as client:
                resp = client.get("/health")
        assert resp.status_code == 200

    def test_multiple_requests_during_lifespan(self) -> None:
        """Scheduler must remain active for multiple requests within one lifespan."""
        with patch.dict(os.environ, {"SCHEDULER_BACKEND": "memory"}):
            from context_hub.main import create_app

            test_app = create_app()
            with TestClient(test_app) as client:
                r1 = client.get("/health")
                r2 = client.get("/health")
        assert r1.status_code == 200
        assert r2.status_code == 200


class TestSchedulerBackendEnvVar:
    """SCHEDULER_BACKEND env var must control store selection in lifespan."""

    def test_memory_backend_env_var_accepted(self) -> None:
        """SCHEDULER_BACKEND=memory must not cause an error during startup."""
        with patch.dict(os.environ, {"SCHEDULER_BACKEND": "memory"}):
            from context_hub.main import create_app

            app = create_app()
            with TestClient(app) as client:
                resp = client.get("/health")
        assert resp.status_code == 200


class TestLifespanShutdownTryFinally:
    """H-5: store.shutdown must be called even if scheduler.shutdown raises."""

    def test_store_shutdown_called_when_scheduler_shutdown_raises(self) -> None:
        """If scheduler.shutdown raises, store.shutdown must still execute."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import FastAPI

        from context_hub.main import lifespan

        mock_scheduler = MagicMock()
        mock_scheduler.shutdown.side_effect = RuntimeError("scheduler exploded")

        mock_store = MagicMock()
        mock_store.bind = MagicMock()
        mock_store.shutdown = AsyncMock()

        app = FastAPI()

        # Patch the local imports inside lifespan
        with (
            patch(
                "context_hub.adapters.scheduler.factory.get_scheduler_store",
                return_value=mock_store,
            ),
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler",
                return_value=mock_scheduler,
            ),
        ):
            async def run() -> None:
                async with lifespan(app):
                    pass  # trigger startup

            with pytest.raises(RuntimeError, match="scheduler exploded"):
                asyncio.run(run())

        # store.shutdown must be called regardless of the RuntimeError
        mock_store.shutdown.assert_called_once_with(graceful=True)

    def test_store_shutdown_called_on_clean_shutdown(self) -> None:
        """store.shutdown must also be called on normal (non-exceptional) shutdown."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import FastAPI

        from context_hub.main import lifespan

        mock_scheduler = MagicMock()
        mock_scheduler.shutdown = MagicMock()  # does not raise

        mock_store = MagicMock()
        mock_store.bind = MagicMock()
        mock_store.shutdown = AsyncMock()

        app = FastAPI()

        with (
            patch(
                "context_hub.adapters.scheduler.factory.get_scheduler_store",
                return_value=mock_store,
            ),
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler",
                return_value=mock_scheduler,
            ),
        ):
            async def run() -> None:
                async with lifespan(app):
                    pass

            asyncio.run(run())

        mock_store.shutdown.assert_called_once_with(graceful=True)
