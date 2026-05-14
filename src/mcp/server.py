"""MCP server skeleton for Context-Hub.

Exposes Context-Hub data to Claude Desktop / Claude Code via MCP protocol.
Tools defined here delegate to the REST API internally.

Transport: stdio (PoC) → HTTP/SSE (production).
Auth: CONTEXT_HUB_API_KEY environment variable.

See 02-api-spec.md Section 6 for the full tool definitions.
"""

from __future__ import annotations

# MCP tools are defined but not yet wired to real data.
# Full implementation in Step 2 (API layer completion).

MCP_TOOLS = [
    {
        "name": "get_project_context",
        "description": "Get project context summary from Context-Hub",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "type": {"type": "string", "enum": ["overview", "full"], "default": "overview"},
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

# TODO (Step 2): Implement MCP server using anthropic mcp SDK
# from mcp.server import Server
# from mcp.server.stdio import stdio_server
#
# async def run_mcp_server():
#     server = Server("context-hub")
#     # Register tools and resources here
#     async with stdio_server() as (read_stream, write_stream):
#         await server.run(read_stream, write_stream, ...)
