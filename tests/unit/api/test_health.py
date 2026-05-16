"""Unit tests for API health endpoint and response envelope."""

import importlib
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from context_hub.main import app

_DEV_KEY = "test-dev-key-for-unit-tests"


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_with_dev_key():
    """TestClient with DEV_API_KEY injected into the auth module."""
    import context_hub.api.middleware.auth as auth_mod

    with patch.object(auth_mod, "_DEV_API_KEY", _DEV_KEY), patch.object(
        auth_mod, "_APP_ENV", "development"
    ):
        yield TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "ok"


class TestAuthMiddleware:
    def test_missing_api_key_returns_401(self, client):
        response = client.get("/api/v1/projects/some-id/context")
        assert response.status_code == 401

    def test_invalid_api_key_returns_401(self, client):
        response = client.get(
            "/api/v1/projects/some-id/context",
            headers={"X-Api-Key": "invalid-key"},
        )
        assert response.status_code == 401

    def test_dev_api_key_env_var_passes_auth(self, client_with_dev_key):
        """DEV_API_KEY from environment passes auth in development mode."""
        response = client_with_dev_key.get(
            "/api/v1/projects/some-id/context",
            headers={"X-Api-Key": _DEV_KEY},
        )
        # Auth passed if not 401; DB may not be available in unit test context
        assert response.status_code != 401

    def test_hardcoded_stub_key_no_longer_works(self, client):
        """The old hardcoded stub key must no longer bypass auth."""
        response = client.get(
            "/api/v1/projects/some-id/context",
            headers={"X-Api-Key": "ctx-hub-dev-stub"},
        )
        assert response.status_code == 401
