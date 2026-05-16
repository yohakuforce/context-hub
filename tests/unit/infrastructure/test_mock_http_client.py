"""Unit tests for MockHttpClient."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.infrastructure.adapters.mock_http_client import MockHttpClient, MockHttpResponse


class TestMockHttpResponse:
    def test_json_returns_data(self):
        response = MockHttpResponse(data={"key": "value"})
        assert response.json() == {"key": "value"}

    def test_raise_for_status_ok(self):
        response = MockHttpResponse(data={}, status_code=200)
        response.raise_for_status()  # should not raise

    def test_raise_for_status_error(self):
        response = MockHttpResponse(data={}, status_code=404)
        with pytest.raises(RuntimeError):
            response.raise_for_status()

    def test_default_status_code_is_200(self):
        response = MockHttpResponse(data={})
        assert response.status_code == 200


class TestMockHttpClient:
    @pytest.fixture
    def temp_fixture(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump({"ok": True, "messages": []}, fh)
            path = Path(fh.name)
        yield path
        path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_returns_fixture_data(self, temp_fixture):
        client = MockHttpClient(fixture_map={"/conversations.history": temp_fixture})
        response = await client.get("/conversations.history")
        assert response.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_get_prefix_match(self, temp_fixture):
        """Client should match if path starts with a registered key."""
        client = MockHttpClient(fixture_map={"/issues": temp_fixture})
        response = await client.get("/issues")
        assert response.json() is not None

    @pytest.mark.asyncio
    async def test_get_unknown_path_raises(self, temp_fixture):
        client = MockHttpClient(fixture_map={"/conversations.history": temp_fixture})
        with pytest.raises(FileNotFoundError):
            await client.get("/unknown/path")

    @pytest.mark.asyncio
    async def test_get_missing_fixture_file_raises(self):
        client = MockHttpClient(
            fixture_map={"/test": Path("/nonexistent/path.json")}
        )
        with pytest.raises(FileNotFoundError):
            await client.get("/test")
