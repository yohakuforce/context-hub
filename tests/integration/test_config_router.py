"""Integration tests for the admin config endpoints and /admin page.

- ADMIN scope is enforced on GET/PUT /api/v1/config.
- GET returns masked secrets in the envelope.
- PUT writes .env (in a temp cwd), reports results, and hot-reloads.
- /admin serves the HTML console shell.

The PUT test changes cwd to a tmp dir so the real ./.env is never touched, and
snapshots/restores the settings singleton so reload() can't pollute other tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from context_hub.main import create_app

_TEST_API_KEY = "config-test-admin-key"
_HEADERS = {"X-Api-Key": _TEST_API_KEY}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Isolate .env writes to the temp dir.
    monkeypatch.chdir(tmp_path)

    # Snapshot the settings singleton so reload_runtime_settings() can't leak
    # test values into other tests.
    from context_hub.config import settings as _settings

    snapshot = {k: getattr(_settings, k) for k in type(_settings).model_fields}

    # Grant ADMIN to the dev key.
    import context_hub.api.middleware.auth as _auth_mod

    monkeypatch.setattr(_auth_mod, "_DEV_API_KEY", _TEST_API_KEY, raising=False)

    # Status endpoint needs a project repo; give it an empty in-memory stub so the
    # tmp-cwd SQLite DB (unmigrated) is never touched.
    from context_hub.api.dependencies import get_project_repo

    class _EmptyRepo:
        async def find_all(self) -> list:
            return []

    app = create_app()
    app.dependency_overrides[get_project_repo] = lambda: _EmptyRepo()
    with TestClient(app) as c:
        yield c

    for k, v in snapshot.items():
        setattr(_settings, k, v)


class TestAuth:
    def test_get_config_requires_key(self, client: TestClient) -> None:
        assert client.get("/api/v1/config").status_code == 401

    def test_get_config_rejects_bad_key(self, client: TestClient) -> None:
        r = client.get("/api/v1/config", headers={"X-Api-Key": "nope"})
        assert r.status_code == 401


class TestGetConfig:
    def test_returns_fields_envelope(self, client: TestClient) -> None:
        r = client.get("/api/v1/config", headers=_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        fields = body["data"]["fields"]
        assert any(f["env"] == "SLACK_BOT_TOKEN" for f in fields)
        # Field shape uses camelCase (restartRequired).
        slack = next(f for f in fields if f["env"] == "SLACK_BOT_TOKEN")
        assert "restartRequired" in slack and slack["secret"] is True


class TestPutConfig:
    def test_set_and_mask_roundtrip(self, client: TestClient) -> None:
        r = client.put(
            "/api/v1/config",
            headers=_HEADERS,
            json={"updates": {"SLACK_BOT_TOKEN": "xoxb-abcd-7777", "GMAIL_QUERY": "label:x"}},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert set(data["changed"]) == {"SLACK_BOT_TOKEN", "GMAIL_QUERY"}
        assert data["reloaded"] is True

        # GET back: secret masked, non-secret raw.
        got = client.get("/api/v1/config", headers=_HEADERS).json()["data"]["fields"]
        fields = {f["env"]: f for f in got}
        assert fields["SLACK_BOT_TOKEN"]["value"] == "••••7777"
        assert fields["GMAIL_QUERY"]["value"] == "label:x"

    def test_unknown_key_rejected(self, client: TestClient) -> None:
        r = client.put(
            "/api/v1/config", headers=_HEADERS, json={"updates": {"BOGUS_KEY": "v"}}
        )
        assert r.status_code == 200
        assert r.json()["data"]["rejected"] == ["BOGUS_KEY"]

    def test_restart_required_reported(self, client: TestClient) -> None:
        r = client.put(
            "/api/v1/config",
            headers=_HEADERS,
            json={"updates": {"DATABASE_URL": "sqlite+aiosqlite:///./t.db"}},
        )
        assert "DATABASE_URL" in r.json()["data"]["restartRequired"]


class TestTestConnection:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post("/api/v1/config/test/slack").status_code == 401

    def test_unconfigured_source_reports_not_ok(self, client: TestClient) -> None:
        # tmp cwd .env has no Slack token → readiness fails, no network call.
        r = client.post("/api/v1/config/test/slack", headers=_HEADERS)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["ok"] is False and data["live"] is False


class TestStatus:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get("/api/v1/status").status_code == 401

    def test_returns_system_snapshot(self, client: TestClient) -> None:
        r = client.get("/api/v1/status", headers=_HEADERS)
        assert r.status_code == 200
        data = r.json()["data"]
        # camelCase keys + expected shape.
        assert "vectorSearchAvailable" in data and "ftsDegraded" in data
        assert "projects" in data and isinstance(data["projects"], list)


class TestAdminPage:
    def test_admin_html_served(self, client: TestClient) -> None:
        r = client.get("/admin")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "Context-Hub" in r.text and "X-Api-Key" in r.text

    def test_admin_html_has_all_tabs(self, client: TestClient) -> None:
        text = client.get("/admin").text
        for tab in ('data-tab="settings"', 'data-tab="sources"', 'data-tab="status"'):
            assert tab in text
