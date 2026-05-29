"""Unit tests for the meeting task extractor (deterministic, no real LLM)."""

from __future__ import annotations

import pytest

from context_hub.infrastructure.llm.base import LLMAdapter, LLMMessage, LLMResponse
from context_hub.services.meeting_task_extractor import extract_meeting_tasks


class _StubLLM(LLMAdapter):
    """Returns a fixed string so extraction is deterministic under test."""

    def __init__(self, content: str) -> None:
        self._content = content

    async def generate(
        self,
        messages: list[LLMMessage],
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        **kwargs: object,
    ) -> LLMResponse:
        return LLMResponse(content=self._content, model="stub", input_tokens=0, output_tokens=0)

    def provider_name(self) -> str:
        return "stub"


class _BoomLLM(LLMAdapter):
    async def generate(self, *args: object, **kwargs: object) -> LLMResponse:
        raise RuntimeError("LLM down")

    def provider_name(self) -> str:
        return "boom"


@pytest.mark.asyncio
async def test_parses_well_formed_json_array() -> None:
    content = (
        '[{"title": "認証APIスキーマ設計レビュー", "assignee": "メンバーA", "dueDate": "2026-06-03"},'
        ' {"title": "マイグレーション失敗の原因特定", "assignee": null, "dueDate": null}]'
    )
    tasks = await extract_meeting_tasks("会議本文", _StubLLM(content))
    assert len(tasks) == 2
    assert tasks[0].title == "認証APIスキーマ設計レビュー"
    assert tasks[0].assignee == "メンバーA"
    assert tasks[0].due_date == "2026-06-03"
    assert tasks[1].assignee is None
    assert tasks[1].due_date is None


@pytest.mark.asyncio
async def test_strips_code_fences_and_surrounding_text() -> None:
    content = 'はい、抽出しました:\n```json\n[{"title": "UIモック提出"}]\n```\n以上です。'
    tasks = await extract_meeting_tasks("会議本文", _StubLLM(content))
    assert len(tasks) == 1
    assert tasks[0].title == "UIモック提出"


@pytest.mark.asyncio
async def test_empty_transcript_returns_empty() -> None:
    assert await extract_meeting_tasks("   ", _StubLLM("[]")) == ()


@pytest.mark.asyncio
async def test_malformed_json_returns_empty() -> None:
    assert await extract_meeting_tasks("本文", _StubLLM("not json at all")) == ()


@pytest.mark.asyncio
async def test_llm_failure_returns_empty_not_raise() -> None:
    assert await extract_meeting_tasks("本文", _BoomLLM()) == ()


@pytest.mark.asyncio
async def test_skips_items_without_title() -> None:
    content = '[{"assignee": "X"}, {"title": ""}, {"title": "有効タスク"}]'
    tasks = await extract_meeting_tasks("本文", _StubLLM(content))
    assert len(tasks) == 1
    assert tasks[0].title == "有効タスク"
