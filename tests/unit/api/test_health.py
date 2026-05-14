"""Unit tests for API health endpoint and response envelope."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


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

    def test_dev_stub_key_passes_auth(self, client):
        # The stub key should pass auth and return 501 (not yet implemented)
        response = client.get(
            "/api/v1/projects/some-id/context",
            headers={"X-Api-Key": "ctx-hub-dev-stub"},
        )
        # 501 means auth passed but logic not yet wired
        assert response.status_code == 501
