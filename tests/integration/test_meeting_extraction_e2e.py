"""E2E: POST a meeting document -> on-prem LLM extracts tasks at ingestion ->
GET meeting returns the persisted extractedTasks (camelCase).

Uses a stub LLM (deterministic JSON) injected via get_llm_adapter, so the full
create -> extract -> persist -> read path is exercised without a real LLM.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from context_hub.api.dependencies import (
    get_document_repo,
    get_embedding,
    get_issue_repo,
    get_job_repo,
    get_llm_adapter,
    get_project_repo,
    get_query_service,
)
from context_hub.application.query_service import QueryService
from context_hub.infrastructure.embedding.mock_adapter import MockEmbeddingAdapter
from context_hub.infrastructure.llm.base import LLMAdapter, LLMMessage, LLMResponse
from context_hub.main import create_app

from tests.integration.test_api_routers import InMemoryProjectRepository
from tests.integration.test_ingestion_service import (
    InMemoryDocumentRepository,
    InMemoryIssueRepository,
    InMemoryJobRepository,
)
from tests.integration.test_issues_router import _make_project

_HEADERS = {"X-Api-Key": "integration-test-dev-key"}

_TASKS_JSON = (
    '[{"title": "認証APIスキーマ設計レビュー", "assignee": "メンバーA", "dueDate": "2026-06-03"},'
    ' {"title": "マイグレーション失敗の原因特定", "assignee": "メンバーB", "dueDate": "2026-06-02"}]'
)


class _StubLLM(LLMAdapter):
    async def generate(self, messages: list[LLMMessage], system_prompt=None,
                       max_tokens=2000, temperature=0.0, **kwargs) -> LLMResponse:
        return LLMResponse(content=_TASKS_JSON, model="stub", input_tokens=0, output_tokens=0)

    def provider_name(self) -> str:
        return "stub"


@pytest.fixture
def repos():
    return (
        InMemoryJobRepository(),
        InMemoryDocumentRepository(),
        InMemoryIssueRepository(),
        InMemoryProjectRepository(),
        MockEmbeddingAdapter(),
    )


@pytest.fixture
def app(repos):
    job_repo, doc_repo, issue_repo, project_repo, embedding = repos
    asyncio.run(project_repo.save(_make_project()))
    app_ = create_app()
    app_.dependency_overrides[get_job_repo] = lambda: job_repo
    app_.dependency_overrides[get_document_repo] = lambda: doc_repo
    app_.dependency_overrides[get_issue_repo] = lambda: issue_repo
    app_.dependency_overrides[get_project_repo] = lambda: project_repo
    app_.dependency_overrides[get_embedding] = lambda: embedding
    app_.dependency_overrides[get_llm_adapter] = lambda: _StubLLM()
    app_.dependency_overrides[get_query_service] = lambda: QueryService(
        document_repo=doc_repo, embedding_provider=embedding
    )
    import context_hub.api.middleware.auth as _auth_mod
    _auth_mod._DEV_API_KEY = "integration-test-dev-key"  # noqa: SLF001
    _auth_mod._APP_ENV = "development"  # noqa: SLF001
    return app_


@pytest.mark.asyncio
async def test_meeting_post_extracts_and_get_returns_tasks(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/documents",
            json={
                "projectId": "proj-001",
                "sourceType": "meeting",
                "externalId": "mtg-e2e-1",
                "title": "定例MTG",
                "text": "認証基盤のリプレースを最優先に決定。マイグレーション失敗を調査。",
            },
            headers=_HEADERS,
        )
        assert create.status_code == 201, create.text
        doc_id = create.json()["data"]["documentId"]

        got = await client.get(
            f"/api/v1/projects/proj-001/meetings/{doc_id}", headers=_HEADERS
        )
    assert got.status_code == 200
    tasks = got.json()["data"]["extractedTasks"]
    assert len(tasks) == 2
    assert tasks[0]["title"] == "認証APIスキーマ設計レビュー"
    assert tasks[0]["suggestedAssignee"] == "メンバーA"
    assert tasks[0]["suggestedDueDate"] == "2026-06-03"
