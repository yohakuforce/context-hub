"""Seed masked sample data into the Context-Hub SQLite DB.

Populates one Project, one meeting Document (task-extractable transcript),
and two assigned Issues so the MCP read-tools and REST issues endpoint
return real (non-empty) data for the AI-PM 5-capability loop demo.

All names/content are fictional and masked — NO real customer data.

Run:
    cd ~/Desktop/01_active/Context-Hub
    source .venv/bin/activate
    python scripts/seed_sample.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime

from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
from context_hub.domain.document.entities import Document, ExtractedMeetingTask
from context_hub.domain.issue.entities import Issue
from context_hub.domain.project.entities import Project, SourceConfig
from context_hub.shared.types import (
    DocumentId,
    IssueId,
    IssuePriority,
    IssueStatus,
    MemberRef,
    ProjectId,
    RawContent,
    SourceType,
    StructuredContent,
)

DB_PATH = os.environ.get("CH_SQLITE_DB", "./data/context_hub.db")
PROJECT_ID = ProjectId("proj-001")
EXTERNAL_PROJECT_ID = "DEMO"
MEETING_DOC_ID = DocumentId("meeting-demo-001")

MEETING_TRANSCRIPT = """\
【定例MTG 議事録（マスク済みサンプル）】
日時: 2026-05-29 10:00-10:40
参加: PM（メンバーA）/ 開発（メンバーB）/ デザイン（メンバーC）

- 決定: 次スプリントは認証基盤のリプレースを最優先とする。
- メンバーB: ログイン APIのリファクタを今週中に着手。レビューはメンバーAが担当。
- メンバーC: 設定画面のUIモックを6/2までに用意する。
- 課題: ステージング環境のDBマイグレーションが2日連続で失敗している。要原因調査。
- 次回までのTODO:
  1. 認証APIの新スキーマ設計レビュー（担当: メンバーA、期限 6/3）
  2. マイグレーション失敗の根本原因特定（担当: メンバーB、期限 6/2）
  3. 設定画面UIモック提出（担当: メンバーC、期限 6/2）
"""

MEMBER_A = MemberRef(external_id="user-a", name="メンバーA")
MEMBER_B = MemberRef(external_id="user-b", name="メンバーB")


def build_project() -> Project:
    now = datetime.utcnow()
    return Project(
        id=PROJECT_ID,
        name="デモPJ — 基幹システム刷新（マスク済）",
        external_project_id=EXTERNAL_PROJECT_ID,
        sources=[
            SourceConfig(
                source_type=SourceType.BACKLOG,
                sync_interval_minutes=60,
                is_enabled=True,
                credentials=None,
                backlog_project_key="DEMO",
            ),
            SourceConfig(
                source_type=SourceType.MEETING,
                sync_interval_minutes=0,
                is_enabled=True,
                credentials=None,
            ),
        ],
        created_at=now,
        updated_at=now,
    )


def build_meeting() -> Document:
    now = datetime.utcnow()
    doc = Document.create(
        project_id=PROJECT_ID,
        source_type=SourceType.MEETING,
        external_id="meeting-2026-05-29",
        raw_content=RawContent(
            text=MEETING_TRANSCRIPT,
            source_url=None,
            author_id=MEMBER_A.external_id,
            created_at=now,
        ),
    )
    # Use a stable document id so demos can reference the meeting directly.
    doc = Document(
        id=MEETING_DOC_ID,
        project_id=doc.project_id,
        source_type=doc.source_type,
        external_id=doc.external_id,
        raw_content=doc.raw_content,
        structured_content=doc.structured_content,
        embedding_vector=doc.embedding_vector,
        ingestion_job_id=doc.ingestion_job_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )
    doc = doc.with_structured_content(
        StructuredContent(
            summary="認証基盤リプレースを最優先に決定。マイグレーション失敗の原因調査が課題。",
            language="ja",
            tags=("認証", "マイグレーション", "UI"),
            entities=(),
        )
    )
    # Tasks the on-prem LLM would extract from this transcript (persisted so the
    # 会議→タスク自動生成 path is deterministic in the demo without a live LLM).
    return doc.with_extracted_tasks(
        (
            ExtractedMeetingTask(title="認証APIの新スキーマ設計レビュー", assignee="メンバーA", due_date="2026-06-03"),
            ExtractedMeetingTask(title="マイグレーション失敗の根本原因特定", assignee="メンバーB", due_date="2026-06-02"),
            ExtractedMeetingTask(title="設定画面UIモック提出", assignee="メンバーC", due_date="2026-06-02"),
        )
    )


def build_issues() -> list[Issue]:
    now = datetime.utcnow()
    return [
        Issue.create(
            project_id=PROJECT_ID,
            source_type=SourceType.BACKLOG,
            external_id="DEMO-101",
            title="認証APIの新スキーマ設計レビュー",
            description="リプレース後の認証APIスキーマを設計しレビューする。",
            status=IssueStatus.IN_PROGRESS,
            priority=IssuePriority.HIGH,
            assignee=MEMBER_A,
            due_date=date(2026, 6, 3),
            labels=["認証", "設計"],
            created_at=now,
            updated_at=now,
        ),
        Issue.create(
            project_id=PROJECT_ID,
            source_type=SourceType.BACKLOG,
            external_id="DEMO-102",
            title="ステージングDBマイグレーション失敗の原因特定",
            description="2日連続で失敗しているマイグレーションの根本原因を特定する。",
            status=IssueStatus.OPEN,
            priority=IssuePriority.URGENT,
            assignee=MEMBER_B,
            due_date=date(2026, 6, 2),
            labels=["インフラ", "bug"],
            created_at=now,
            updated_at=now,
        ),
    ]


async def main() -> None:
    project_repo = SqliteProjectRepository(DB_PATH)
    document_repo = SqliteDocumentRepository(DB_PATH)
    issue_repo = SqliteIssueRepository(DB_PATH)

    project = build_project()
    await project_repo.save(project)

    meeting = build_meeting()
    await document_repo.save(meeting)

    issues = build_issues()
    await issue_repo.save_many(issues)

    print(f"DB: {DB_PATH}")
    print(f"  project: {project.id} ({project.external_project_id})")
    print(f"  meeting: {meeting.id} (external_id={meeting.external_id})")
    for issue in issues:
        print(f"  issue:   {issue.id} {issue.external_id} -> {issue.assignee.name}")


if __name__ == "__main__":
    asyncio.run(main())
