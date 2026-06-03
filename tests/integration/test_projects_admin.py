"""Integration tests for project / source-config CRUD (admin GUI write API).

Uses an in-memory project repo via dependency override, and the dev API key for
auth — mirroring tests/integration/test_api_routers.py.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from context_hub.api.dependencies import get_project_repo
from context_hub.domain.project.repository import ProjectRepository
from context_hub.main import create_app
from context_hub.shared.types import ProjectId

_KEY = "projadmin-test-key"
_H = {"X-Api-Key": _KEY}


class InMemoryProjectRepository(ProjectRepository):
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    async def find_by_id(self, project_id: ProjectId):  # type: ignore[override]
        return self._store.get(str(project_id))

    async def find_all(self):  # type: ignore[override]
        return list(self._store.values())

    async def find_by_external_id(self, external_project_id: str):  # type: ignore[override]
        for p in self._store.values():
            if getattr(p, "external_project_id", None) == external_project_id:
                return p
        return None

    async def save(self, project):  # type: ignore[override]
        self._store[str(project.id)] = project
        return project

    async def delete(self, project_id: ProjectId) -> None:  # type: ignore[override]
        self._store.pop(str(project_id), None)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    import context_hub.api.middleware.auth as _auth_mod

    monkeypatch.setattr(_auth_mod, "_DEV_API_KEY", _KEY, raising=False)

    repo = InMemoryProjectRepository()
    app = create_app()
    app.dependency_overrides[get_project_repo] = lambda: repo
    with TestClient(app) as c:
        yield c


def _create(client: TestClient, name: str = "Acme") -> str:
    r = client.post("/api/v1/projects", headers=_H, json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


class TestProjectCrud:
    def test_create_requires_auth(self, client: TestClient) -> None:
        assert client.post("/api/v1/projects", json={"name": "x"}).status_code == 401

    def test_create_and_list_detailed(self, client: TestClient) -> None:
        pid = _create(client, "Acme")
        r = client.get("/api/v1/projects/detailed", headers=_H)
        assert r.status_code == 200
        projects = r.json()["data"]
        assert any(p["id"] == pid and p["name"] == "Acme" for p in projects)

    def test_update_name(self, client: TestClient) -> None:
        pid = _create(client, "Old")
        r = client.put(f"/api/v1/projects/{pid}", headers=_H, json={"name": "New"})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "New"

    def test_delete(self, client: TestClient) -> None:
        pid = _create(client)
        assert client.delete(f"/api/v1/projects/{pid}", headers=_H).status_code == 200
        listed = client.get("/api/v1/projects/detailed", headers=_H).json()["data"]
        assert all(p["id"] != pid for p in listed)

    def test_update_missing_404(self, client: TestClient) -> None:
        r = client.put("/api/v1/projects/nope", headers=_H, json={"name": "x"})
        assert r.status_code == 404


class TestSourceCrud:
    def test_add_source(self, client: TestClient) -> None:
        pid = _create(client)
        r = client.put(
            f"/api/v1/projects/{pid}/sources/slack",
            headers=_H,
            json={"isEnabled": True, "syncIntervalMinutes": 30, "channelIds": ["C1", "C2"]},
        )
        assert r.status_code == 200, r.text
        sources = {s["sourceType"]: s for s in r.json()["data"]["sources"]}
        assert sources["slack"]["isEnabled"] is True
        assert sources["slack"]["syncIntervalMinutes"] == 30
        assert sources["slack"]["channelIds"] == ["C1", "C2"]

    def test_upsert_replaces_existing(self, client: TestClient) -> None:
        pid = _create(client)
        client.put(
            f"/api/v1/projects/{pid}/sources/slack",
            headers=_H,
            json={"isEnabled": True, "syncIntervalMinutes": 30},
        )
        r = client.put(
            f"/api/v1/projects/{pid}/sources/slack",
            headers=_H,
            json={"isEnabled": False, "syncIntervalMinutes": 60},
        )
        sources = {s["sourceType"]: s for s in r.json()["data"]["sources"]}
        assert len([s for s in r.json()["data"]["sources"] if s["sourceType"] == "slack"]) == 1
        assert sources["slack"]["isEnabled"] is False
        assert sources["slack"]["syncIntervalMinutes"] == 60

    def test_remove_source(self, client: TestClient) -> None:
        pid = _create(client)
        client.put(
            f"/api/v1/projects/{pid}/sources/backlog",
            headers=_H,
            json={"isEnabled": True, "syncIntervalMinutes": 15, "backlogProjectKey": "PROJ"},
        )
        r = client.delete(f"/api/v1/projects/{pid}/sources/backlog", headers=_H)
        assert r.status_code == 200
        assert r.json()["data"]["sources"] == []

    def test_invalid_source_type_422(self, client: TestClient) -> None:
        pid = _create(client)
        r = client.put(
            f"/api/v1/projects/{pid}/sources/meeting",  # not a configurable adapter
            headers=_H,
            json={"isEnabled": True},
        )
        assert r.status_code == 422
