"""Extract actionable tasks from a meeting transcript via the on-prem LLM.

Runs inside Context-Hub (the on-prem boundary) so raw customer transcripts are
never sent to an external/pay-per-token API — only through the configured
LLMAdapter (claude-code / ollama / mock). The result is persisted on the
meeting Document at ingestion time, so repeated reads return a stable task list
(important: a missed or drifting task is treated as a serious incident).

The LLM is asked to return a strict JSON array. Parsing is defensive: code
fences are stripped and malformed output yields an empty list rather than an
error, because downstream consumers (AI-PM) tolerate an empty task list but not
a 500.
"""

from __future__ import annotations

import json
import re
import sys

from context_hub.domain.document.entities import ExtractedMeetingTask
from context_hub.infrastructure.llm.base import LLMAdapter, LLMMessage

_SYSTEM_PROMPT = (
    "あなたはプロジェクトマネジメント支援AIです。会議の文字起こしから、"
    "担当者が着手すべき具体的なアクションタスクを抽出します。"
    "出力は必ず JSON 配列のみとし、前後に説明文やコードフェンスを付けないでください。"
    "各要素は {\"title\": string, \"assignee\": string|null, \"dueDate\": string|null} の形式。"
    "title は動詞で始まる簡潔なタスク名。assignee は担当者名（不明なら null）。"
    "dueDate は YYYY-MM-DD 形式（不明なら null）。タスクが無ければ空配列 [] を返す。"
)

_USER_TEMPLATE = "次の会議文字起こしからタスクを抽出してください。\n\n---\n{transcript}\n---"

# Cap to avoid a runaway transcript blowing the context / cost.
_MAX_TRANSCRIPT_CHARS = 12000


async def extract_meeting_tasks(
    transcript: str,
    llm: LLMAdapter,
) -> tuple[ExtractedMeetingTask, ...]:
    """Extract tasks from a transcript. Returns () on empty input or parse failure."""
    text = (transcript or "").strip()
    if not text:
        return ()

    prompt = _USER_TEMPLATE.format(transcript=text[:_MAX_TRANSCRIPT_CHARS])
    messages = [LLMMessage(role="user", content=prompt)]
    try:
        response = await llm.generate(
            messages=messages,
            system_prompt=_SYSTEM_PROMPT,
            max_tokens=2000,
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001 — extraction must never break ingestion
        sys.stderr.write(f"meeting task extraction LLM call failed: {exc}\n")
        sys.stderr.flush()
        return ()

    return _parse_tasks(response.content)


def _parse_tasks(raw: str) -> tuple[ExtractedMeetingTask, ...]:
    payload = _extract_json_array(raw)
    if payload is None:
        sys.stderr.write("meeting task extraction: no JSON array found in LLM output\n")
        sys.stderr.flush()
        return ()

    try:
        items = json.loads(payload)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"meeting task extraction: JSON parse error: {exc}\n")
        sys.stderr.flush()
        return ()

    if not isinstance(items, list):
        return ()

    tasks: list[ExtractedMeetingTask] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        assignee = item.get("assignee")
        due_date = item.get("dueDate")
        if due_date is None:
            due_date = item.get("due_date")
        tasks.append(
            ExtractedMeetingTask(
                title=title.strip(),
                assignee=_clean(assignee),
                due_date=_clean(due_date),
            )
        )
    return tuple(tasks)


def _clean(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _extract_json_array(raw: str) -> str | None:
    """Return the first top-level JSON array substring, stripping code fences."""
    if not raw:
        return None
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    return cleaned[start : end + 1]
