"""MCP (Model Context Protocol) server for Context-Hub.

This module is a first-class entry point on par with the HTTP REST API.
MCP tools are thin adapters that delegate to the shared QueryService — the same
service used by the HTTP layer.

Transport: stdio (default for Claude Desktop / Claude Code integration).
Auth: Not enforced in v0.1.0. MCP stdio is designed for localhost-only operation.
      Full authentication (bcrypt + ConsumerRepository) will be added in v0.2.0.

Protocol version: see ``MCP_PROTOCOL_VERSION`` in ``src/mcp/__init__.py``.

Tool definitions are aligned with 02-api-spec.md Section 6.
"""

from __future__ import annotations

import asyncio
import json
import sys

from context_hub.mcp import MCP_PROTOCOL_VERSION

# JSON-RPC request/response IDs can be str, int, or None per the spec.
_RequestId = str | int | None

# ---------------------------------------------------------------------------
# Tool definitions (JSON Schema, MCP wire format)
# ---------------------------------------------------------------------------

MCP_TOOLS: list[dict[str, object]] = [
    {
        "name": "get_project_context",
        "description": "Get project context summary from Context-Hub",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["overview", "full"],
                    "default": "overview",
                },
            },
            "required": ["projectId"],
        },
    },
    {
        "name": "search_context",
        "description": "Search project context using hybrid vector + keyword search",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "query": {"type": "string"},
                "topK": {"type": "integer", "default": 5},
            },
            "required": ["projectId", "query"],
        },
    },
    {
        "name": "get_issues",
        "description": "Get Backlog or Redmine issues for a project",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "source": {"type": "string", "enum": ["backlog", "redmine"]},
                "status": {"type": "string", "default": "open"},
            },
            "required": ["projectId", "source"],
        },
    },
    {
        "name": "get_issue_detail",
        "description": "Get detailed information about a specific issue including comments",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "issueId": {"type": "string"},
            },
            "required": ["projectId", "issueId"],
        },
    },
    {
        "name": "get_meeting",
        "description": "Get meeting transcript and summary",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "meetingId": {"type": "string"},
            },
            "required": ["projectId", "meetingId"],
        },
    },
    {
        "name": "get_members",
        "description": "Get project team members",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
            },
            "required": ["projectId"],
        },
    },
    {
        "name": "trigger_sync",
        "description": "Trigger incremental sync for a data source",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "source": {"type": "string", "enum": ["slack", "backlog", "redmine"]},
            },
            "required": ["projectId", "source"],
        },
    },
]


# ---------------------------------------------------------------------------
# JSON-RPC message helpers (stdio transport)
# ---------------------------------------------------------------------------


def _write_message(msg: dict[str, object]) -> None:
    """Write a JSON-RPC 2.0 message to stdout (stdio transport).

    Uses the binary buffer directly to guarantee UTF-8 encoding regardless of
    the platform locale or ``PYTHONIOENCODING`` setting.

    Args:
        msg: The JSON-RPC message dict to serialise and write.
    """
    line = json.dumps(msg, ensure_ascii=False)
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def _error_response(req_id: _RequestId, code: int, message: str) -> dict[str, object]:
    """Build a JSON-RPC error response.

    Args:
        req_id:  The request id to echo back.
        code:    JSON-RPC error code.
        message: Human-readable error message.

    Returns:
        A JSON-RPC 2.0 error response dict.
    """
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


def _ok_response(req_id: _RequestId, result: object) -> dict[str, object]:
    """Build a JSON-RPC success response.

    Args:
        req_id: The request id to echo back.
        result: The result payload.

    Returns:
        A JSON-RPC 2.0 success response dict.
    """
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


# ---------------------------------------------------------------------------
# Request handler (thin adapter over QueryService)
# ---------------------------------------------------------------------------


async def _handle_request(request: dict[str, object]) -> dict[str, object] | None:
    """Dispatch a single JSON-RPC 2.0 request and return the response.

    Notifications (requests without an ``id``) are processed but return None.

    Args:
        request: The parsed JSON-RPC request dict.

    Returns:
        A JSON-RPC response dict, or None if the request was a notification.
    """
    req_id: _RequestId = request.get("id")  # type: ignore[assignment]
    method = str(request.get("method", ""))
    params: dict[str, object] = request.get("params") or {}  # type: ignore[assignment]

    # --- Initialise handshake ---
    if method == "initialize":
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "context-hub",
                "version": "0.1.0",
            },
        }
        if req_id is not None:
            return _ok_response(req_id, result)
        return None

    # --- Tool listing ---
    if method == "tools/list":
        tools_result: dict[str, object] = {"tools": MCP_TOOLS}
        if req_id is not None:
            return _ok_response(req_id, tools_result)
        return None

    # --- Tool call ---
    if method == "tools/call":
        tool_name = str(params.get("name", ""))
        tool_args = params.get("arguments")
        tool_input: dict[str, object] = tool_args if isinstance(tool_args, dict) else {}
        response_content = await _dispatch_tool(tool_name, tool_input)
        content_text = json.dumps(response_content, ensure_ascii=False)
        call_result: dict[str, object] = {
            "content": [{"type": "text", "text": content_text}]
        }
        if req_id is not None:
            return _ok_response(req_id, call_result)
        return None

    # --- Unknown method ---
    if req_id is not None:
        return _error_response(req_id, -32601, f"Method not found: {method}")
    return None


async def _dispatch_tool(name: str, args: dict[str, object]) -> dict[str, object]:
    """Route a tool call to the appropriate handler.

    Args:
        name: MCP tool name.
        args: Tool arguments (validated by the MCP client against inputSchema).

    Returns:
        A dict to be serialised as the tool result content.
    """
    if name == "search_context":
        return await _tool_search_context(args)
    if name == "get_project_context":
        return await _tool_get_project_context(args)
    if name == "get_members":
        return await _tool_get_members(args)
    if name == "get_meeting":
        return await _tool_get_meeting(args)
    if name == "get_issues":
        return await _tool_get_issues(args)
    if name == "get_issue_detail":
        return await _tool_get_issue_detail(args)
    # Unknown / unimplemented tools
    return {
        "tool": name,
        "status": "stub",
        "message": f"Tool '{name}' will be fully implemented in v0.2.",
        "args": args,
    }


async def _tool_search_context(args: dict[str, object]) -> dict[str, object]:
    """Execute hybrid search via QueryService.

    Args:
        args: Must contain ``projectId`` and ``query``; optionally ``topK``.

    Returns:
        A dict with ``results`` list or an ``error`` key on failure.
    """
    project_id = str(args.get("projectId", ""))
    query_text = str(args.get("query", ""))
    raw_top_k = args.get("topK", 5)
    top_k = max(1, min(int(raw_top_k) if isinstance(raw_top_k, (int, float, str)) else 5, 100))

    if not project_id or not query_text:
        return {"error": "projectId and query are required"}

    try:
        from context_hub.application.query_service import QueryService
        from context_hub.config.profiles import get_profile_settings
        from context_hub.infrastructure.embedding.factory import get_embedding_provider
        from context_hub.shared.types import ProjectId

        settings = get_profile_settings()
        embedding_provider = get_embedding_provider(settings.embedding_provider)

        from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository

        db_path = settings.ch_sqlite_db or "./data/context_hub.db"
        document_repo = SqliteDocumentRepository(db_path)
        service = QueryService(
            document_repo=document_repo,
            embedding_provider=embedding_provider,
        )
        results = await service.search(
            project_id=ProjectId(project_id),
            query=query_text,
            top_k=top_k,
        )
        return {
            "results": [
                {
                    "score": r.score,
                    "title": r.title,
                    "snippet": r.snippet,
                    "documentId": str(r.document.id),
                }
                for r in results
            ]
        }
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"search_context failed: {exc}\n")
        sys.stderr.flush()
        return {"error": "Search failed. See server logs for details.", "results": []}


async def _tool_get_project_context(args: dict[str, object]) -> dict[str, object]:
    """Return project context summary via SQLite repos.

    Args:
        args: Must contain ``projectId``; optionally ``type`` (overview | full).

    Returns:
        A dict with project summary fields or an ``error`` key on failure.
    """
    project_id = str(args.get("projectId", ""))
    if not project_id:
        return {"error": "projectId is required"}

    try:
        from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
        from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
        from context_hub.adapters.sqlite.project_repository import SqliteProjectRepository
        from context_hub.config.profiles import get_profile_settings
        from context_hub.shared.types import ProjectId

        settings = get_profile_settings()
        db_path = settings.ch_sqlite_db or "./data/context_hub.db"

        project_repo = SqliteProjectRepository(db_path)
        document_repo = SqliteDocumentRepository(db_path)
        issue_repo = SqliteIssueRepository(db_path)

        pid = ProjectId(project_id)
        project = await project_repo.find_by_id(pid)
        if project is None:
            return {"error": "Project not found"}

        doc_count = await document_repo.count_by_project(pid)
        issue_count = await issue_repo.count_by_project(pid)
        active_sources = [s.source_type.value for s in project.sources if s.is_enabled]

        return {
            "projectId": project_id,
            "name": project.name,
            "summary": f"Project '{project.name}' has {doc_count} documents and {issue_count} issues.",
            "activeSources": active_sources,
            "documentCount": doc_count,
            "issueCount": issue_count,
        }
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"get_project_context failed: {exc}\n")
        sys.stderr.flush()
        return {"error": "get_project_context failed. See server logs for details."}


async def _tool_get_members(args: dict[str, object]) -> dict[str, object]:
    """Return project member information aggregated from issues via SQLite.

    Args:
        args: Must contain ``projectId``.

    Returns:
        A dict with ``members`` list or an ``error`` key on failure.
    """
    project_id = str(args.get("projectId", ""))
    if not project_id:
        return {"error": "projectId is required"}

    try:
        from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
        from context_hub.config.profiles import get_profile_settings
        from context_hub.shared.types import ProjectId

        settings = get_profile_settings()
        db_path = settings.ch_sqlite_db or "./data/context_hub.db"

        issue_repo = SqliteIssueRepository(db_path)
        pid = ProjectId(project_id)
        issues = await issue_repo.find_by_project(pid, limit=500)

        member_map: dict[str, dict[str, object]] = {}
        for issue in issues:
            if issue.assignee:
                key = issue.assignee.external_id
                if key not in member_map:
                    member_map[key] = {
                        "externalId": key,
                        "name": issue.assignee.name,
                        "sources": [issue.source_type.value],
                        "assignedIssueCount": 0,
                    }
                else:
                    sources = member_map[key]["sources"]
                    assert isinstance(sources, list)
                    if issue.source_type.value not in sources:
                        sources = [*sources, issue.source_type.value]
                    member_map[key] = {**member_map[key], "sources": sources}
                member_map[key] = {
                    **member_map[key],
                    "assignedIssueCount": int(member_map[key]["assignedIssueCount"]) + 1,
                }

        return {"members": list(member_map.values())}
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"get_members failed: {exc}\n")
        sys.stderr.flush()
        return {"error": "get_members failed. See server logs for details."}


async def _tool_get_meeting(args: dict[str, object]) -> dict[str, object]:
    """Return full detail of a single meeting document via SQLite.

    Args:
        args: Must contain ``projectId`` and ``meetingId``.

    Returns:
        A dict with meeting detail fields or an ``error`` key on failure.
    """
    project_id = str(args.get("projectId", ""))
    meeting_id = str(args.get("meetingId", ""))
    if not project_id or not meeting_id:
        return {"error": "projectId and meetingId are required"}

    try:
        from context_hub.adapters.sqlite.document_repository import SqliteDocumentRepository
        from context_hub.config.profiles import get_profile_settings
        from context_hub.shared.types import DocumentId, SourceType

        settings = get_profile_settings()
        db_path = settings.ch_sqlite_db or "./data/context_hub.db"

        document_repo = SqliteDocumentRepository(db_path)
        doc = await document_repo.find_by_id(DocumentId(meeting_id))

        if doc is None or doc.source_type != SourceType.MEETING:
            return {"error": "Meeting not found"}

        title = _mcp_derive_title(doc)
        summary = doc.structured_content.summary if doc.structured_content else ""
        return {
            "meetingId": meeting_id,
            "projectId": project_id,
            "title": title,
            "meetingAt": doc.raw_content.created_at.isoformat(),
            "participants": [],
            "rawTranscript": doc.raw_content.text,
            "summary": summary,
            "decisions": [],
            "extractedTasks": [
                {
                    "title": t.title,
                    "suggestedAssignee": t.assignee,
                    "suggestedDueDate": t.due_date,
                }
                for t in doc.extracted_tasks
            ],
        }
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"get_meeting failed: {exc}\n")
        sys.stderr.flush()
        return {"error": "get_meeting failed. See server logs for details."}


async def _tool_get_issues(args: dict[str, object]) -> dict[str, object]:
    """Return issues for a project from Backlog or Redmine via SQLite.

    Args:
        args: Must contain ``projectId`` and ``source``; optionally ``status``.

    Returns:
        A dict with ``issues`` list or an ``error`` key on failure.
    """
    project_id = str(args.get("projectId", ""))
    source = str(args.get("source", ""))
    status = str(args.get("status", "open")) if args.get("status") else "open"

    if not project_id or not source:
        return {"error": "projectId and source are required"}

    try:
        from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
        from context_hub.config.profiles import get_profile_settings
        from context_hub.shared.types import IssueStatus, ProjectId, SourceType

        settings = get_profile_settings()
        db_path = settings.ch_sqlite_db or "./data/context_hub.db"

        issue_repo = SqliteIssueRepository(db_path)
        pid = ProjectId(project_id)

        try:
            source_type = SourceType(source)
        except ValueError:
            return {"error": f"Unknown source: {source!r}. Expected backlog or redmine."}

        issue_status: IssueStatus | None = None
        if status:
            try:
                issue_status = IssueStatus(status)
            except ValueError:
                return {"error": f"Unknown status: {status!r}"}

        issues = await issue_repo.find_by_project(
            pid,
            source_type=source_type,
            status=issue_status,
            limit=50,
        )

        return {
            "projectId": project_id,
            "source": source,
            "issues": [
                {
                    "issueId": str(issue.id),
                    "externalId": issue.external_id,
                    "title": issue.title,
                    "status": issue.status.value,
                    "priority": issue.priority.value,
                    "assignee": (
                        {"externalId": issue.assignee.external_id, "name": issue.assignee.name}
                        if issue.assignee
                        else None
                    ),
                    "dueDate": issue.due_date.isoformat() if issue.due_date else None,
                    "labels": list(issue.labels),
                    "commentCount": len(issue.comments),
                    "updatedAt": issue.updated_at.isoformat(),
                }
                for issue in issues
            ],
            "total": len(issues),
        }
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"get_issues failed: {exc}\n")
        sys.stderr.flush()
        return {"error": "get_issues failed. See server logs for details."}


async def _tool_get_issue_detail(args: dict[str, object]) -> dict[str, object]:
    """Return detailed information about a specific issue including comments.

    Args:
        args: Must contain ``projectId`` and ``issueId``.

    Returns:
        A dict with issue detail fields or an ``error`` key on failure.
    """
    project_id = str(args.get("projectId", ""))
    issue_id = str(args.get("issueId", ""))

    if not project_id or not issue_id:
        return {"error": "projectId and issueId are required"}

    try:
        from context_hub.adapters.sqlite.issue_repository import SqliteIssueRepository
        from context_hub.config.profiles import get_profile_settings
        from context_hub.shared.types import IssueId

        settings = get_profile_settings()
        db_path = settings.ch_sqlite_db or "./data/context_hub.db"

        issue_repo = SqliteIssueRepository(db_path)
        issue = await issue_repo.find_by_id(IssueId(issue_id))

        if issue is None or str(issue.project_id) != project_id:
            return {"error": "Issue not found"}

        return {
            "issueId": str(issue.id),
            "projectId": project_id,
            "externalId": issue.external_id,
            "sourceType": issue.source_type.value,
            "title": issue.title,
            "description": issue.description,
            "status": issue.status.value,
            "priority": issue.priority.value,
            "assignee": (
                {"externalId": issue.assignee.external_id, "name": issue.assignee.name}
                if issue.assignee
                else None
            ),
            "dueDate": issue.due_date.isoformat() if issue.due_date else None,
            "labels": list(issue.labels),
            "comments": [
                {
                    "commentId": str(c.id),
                    "author": {"externalId": c.author.external_id, "name": c.author.name},
                    "body": c.body,
                    "createdAt": c.created_at.isoformat(),
                }
                for c in issue.comments
            ],
            "commentCount": len(issue.comments),
            "createdAt": issue.created_at.isoformat(),
            "updatedAt": issue.updated_at.isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"get_issue_detail failed: {exc}\n")
        sys.stderr.flush()
        return {"error": "get_issue_detail failed. See server logs for details."}


def _mcp_derive_title(doc: object) -> str:
    """Derive a display title from a document (mirrors _derive_title in projects router).

    Args:
        doc: A Document domain object.

    Returns:
        A short title string (at most 80 characters).
    """
    if doc.structured_content and doc.structured_content.summary:  # type: ignore[union-attr]
        return doc.structured_content.summary[:80]  # type: ignore[union-attr]
    raw = doc.raw_content.text or ""  # type: ignore[union-attr]
    first_line = raw.split("\n")[0].strip()
    return first_line[:80] if first_line else f"[{doc.source_type.value}]"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Stdio transport entry point
# ---------------------------------------------------------------------------


async def run_stdio() -> None:
    """Run the MCP server over stdio transport (blocking until EOF).

    Reads JSON-RPC 2.0 messages line-by-line from stdin,
    processes each, and writes responses to stdout.

    Authentication is not enforced in v0.1.0. The stdio transport is intended
    for localhost-only operation (Claude Desktop / Claude Code on the same
    machine). Full auth will be added in v0.2.0.
    """
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            line = await reader.readline()
        except Exception:  # noqa: BLE001
            break
        if not line:
            break
        raw = line.decode("utf-8").strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as exc:
            _write_message(
                _error_response(None, -32700, f"Parse error: {exc}")
            )
            continue
        response = await _handle_request(request)
        if response is not None:
            _write_message(response)


def main() -> None:
    """Synchronous entry point for the MCP stdio server."""
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
