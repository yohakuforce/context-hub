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
    """Route a tool call to the appropriate QueryService method.

    search_context delegates to QueryService.search; all other tools return
    a stub response for v0.1 (full implementation in v0.2).

    Args:
        name: MCP tool name.
        args: Tool arguments (validated by the MCP client against inputSchema).

    Returns:
        A dict to be serialised as the tool result content.
    """
    if name == "search_context":
        return await _tool_search_context(args)
    # v0.1: remaining tools return a stub with a clear roadmap message
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
