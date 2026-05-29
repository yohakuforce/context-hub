"""Wire-format contract lock: API schemas MUST serialize as camelCase.

Context-Hub's REST responses are consumed by AI-Project-Manager's
HttpContextHubClient and (planned) @yohakuforce/core, both of which read
camelCase keys (projectId, externalId, sourceType, ...). Per 02-api-spec.md the
wire contract is camelCase.

These schemas internally use snake_case field names; the camelCase contract is
produced by the CamelModel base (alias_generator=to_camel). If anyone drops that
base or reverts to plain BaseModel, the cross-service integration breaks
silently at the JSON boundary — so this test fails loudly instead.
"""

from __future__ import annotations

from context_hub.api.schemas.issues import AssigneeSchema, IssueSchema
from context_hub.api.schemas.projects import (
    ExtractedTask,
    MeetingDetailResponse,
    MemberResponse,
    ProjectContextResponse,
)
from context_hub.api.schemas.query import QueryResultItem
from context_hub.api.schemas.sync import JobStatusResponse
from context_hub.api.schemas.documents import DocumentResponse


def _dump_keys(model) -> set[str]:
    """Serialize the way FastAPI does for responses (by_alias=True)."""
    return set(model.model_dump(by_alias=True).keys())


def test_project_context_response_is_camel_case():
    model = ProjectContextResponse(
        project_id="proj-001",
        name="テストプロジェクト",
        summary="サマリ",
        active_sources=["slack"],
        last_synced_at={"slack": "2026-05-29T00:00:00Z"},
        document_count=10,
        issue_count=3,
    )
    keys = _dump_keys(model)
    assert {"projectId", "activeSources", "lastSyncedAt", "documentCount", "issueCount"} <= keys
    assert not {"project_id", "active_sources", "document_count", "issue_count"} & keys


def test_member_response_is_camel_case():
    model = MemberResponse(
        external_id="123",
        name="田中 太郎",
        sources=["backlog"],
        assigned_issue_count=5,
        last_activity_at="2026-05-29T00:00:00Z",
    )
    keys = _dump_keys(model)
    assert {"externalId", "assignedIssueCount", "lastActivityAt"} <= keys
    assert not {"external_id", "assigned_issue_count", "last_activity_at"} & keys


def test_issue_schema_is_camel_case():
    model = IssueSchema(
        id="i-1",
        source_type="backlog",
        external_id="42",
        title="ログイン修正",
        description="...",
        status="in_progress",
        priority="high",
        assignee=AssigneeSchema(external_id="123", name="田中 太郎"),
        due_date="2026-05-30",
        labels=["bug"],
        comment_count=3,
        created_at="2026-05-10T09:00:00Z",
        updated_at="2026-05-13T18:00:00Z",
    )
    keys = _dump_keys(model)
    assert {"sourceType", "externalId", "dueDate", "commentCount", "createdAt", "updatedAt"} <= keys
    assert not {"source_type", "external_id", "due_date", "comment_count"} & keys
    # nested assignee must also be camelCase
    assert set(model.model_dump(by_alias=True)["assignee"].keys()) == {"externalId", "name"}


def test_meeting_detail_response_is_camel_case():
    model = MeetingDetailResponse(
        id="m-1",
        title="週次会議",
        meeting_at="2026-05-13T10:00:00Z",
        participants=["田中 太郎"],
        raw_transcript="...",
        summary="...",
        decisions=["API確定"],
        extracted_tasks=[
            ExtractedTask(
                title="API仕様作成",
                suggested_assignee="田中 太郎",
                suggested_due_date="2026-05-20",
            )
        ],
    )
    dumped = model.model_dump(by_alias=True)
    keys = set(dumped.keys())
    assert {"meetingAt", "rawTranscript", "extractedTasks"} <= keys
    assert not {"meeting_at", "raw_transcript", "extracted_tasks"} & keys
    task_keys = set(dumped["extractedTasks"][0].keys())
    assert {"suggestedAssignee", "suggestedDueDate"} <= task_keys
    assert not {"suggested_assignee", "suggested_due_date"} & task_keys


def test_query_result_item_is_camel_case():
    model = QueryResultItem(
        document_id="d-1",
        source_type="meeting",
        title="設計会議",
        snippet="JWT で合意",
        score=0.92,
        relevance_reason="認証設計の決定",
    )
    keys = _dump_keys(model)
    assert {"documentId", "sourceType", "relevanceReason"} <= keys
    assert not {"document_id", "source_type", "relevance_reason"} & keys


def test_job_status_response_is_camel_case():
    model = JobStatusResponse(
        job_id="j-1",
        project_id="proj-001",
        source_type="backlog",
        status="completed",
        items_processed=5,
        errors=[],
        started_at="2026-05-29T00:00:00Z",
        finished_at="2026-05-29T00:01:00Z",
    )
    keys = _dump_keys(model)
    assert {"jobId", "projectId", "sourceType", "itemsProcessed", "startedAt", "finishedAt"} <= keys
    assert not {"job_id", "project_id", "items_processed"} & keys


def test_document_response_is_camel_case():
    model = DocumentResponse(
        document_id="d-1",
        project_id="proj-001",
        source_type="meeting",
        external_id="ext-1",
        embedded=True,
        created_at="2026-05-29T00:00:00Z",
        updated_at="2026-05-29T00:00:00Z",
    )
    keys = _dump_keys(model)
    assert {"documentId", "projectId", "sourceType", "externalId", "createdAt", "updatedAt"} <= keys
    assert not {"document_id", "project_id", "source_type", "external_id"} & keys


def test_snake_case_input_still_accepted():
    """populate_by_name=True keeps internal/snake_case construction working."""
    model = ProjectContextResponse(
        project_id="proj-001",
        name="p",
        summary="s",
        active_sources=[],
        last_synced_at={},
        document_count=0,
        issue_count=0,
    )
    assert model.project_id == "proj-001"
