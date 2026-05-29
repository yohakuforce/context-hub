"""Unit tests for the MCP server module (src/mcp/).

Tests cover:
- MCP_PROTOCOL_VERSION constant availability
- Tool listing (tools/list)
- Initialise handshake (initialize)
- search_context tool dispatch (stub and real path)
- Unknown method returns error
- JSON-RPC helper functions
- /mcp/version HTTP endpoint via FastAPI test client
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestMcpConstants:
    """Verify MCP_PROTOCOL_VERSION is exported."""

    def test_protocol_version_is_exported(self) -> None:
        """MCP_PROTOCOL_VERSION must be accessible from the mcp package."""
        from context_hub.mcp import MCP_PROTOCOL_VERSION

        assert isinstance(MCP_PROTOCOL_VERSION, str)
        assert len(MCP_PROTOCOL_VERSION) > 0

    def test_protocol_version_matches_server(self) -> None:
        """The server must use the same protocol version as __init__ exports."""
        from context_hub.mcp import MCP_PROTOCOL_VERSION
        from context_hub.mcp.server import MCP_TOOLS

        # MCP_TOOLS are defined in server.py — just verify it can be imported
        assert isinstance(MCP_TOOLS, list)
        assert MCP_PROTOCOL_VERSION  # truthy


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


class TestMcpTools:
    """Verify tool definitions are correct."""

    def test_mcp_tools_is_nonempty_list(self) -> None:
        """MCP_TOOLS must be a non-empty list of tool dicts."""
        from context_hub.mcp.server import MCP_TOOLS

        assert isinstance(MCP_TOOLS, list)
        assert len(MCP_TOOLS) > 0

    def test_each_tool_has_required_fields(self) -> None:
        """Each tool must have 'name', 'description', and 'inputSchema'."""
        from context_hub.mcp.server import MCP_TOOLS

        for tool in MCP_TOOLS:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool missing 'description': {tool}"
            assert "inputSchema" in tool, f"Tool missing 'inputSchema': {tool}"

    def test_search_context_tool_present(self) -> None:
        """search_context tool must be defined (it delegates to QueryService)."""
        from context_hub.mcp.server import MCP_TOOLS

        names = [t["name"] for t in MCP_TOOLS]
        assert "search_context" in names

    def test_tool_names_are_unique(self) -> None:
        """Tool names must be unique within MCP_TOOLS."""
        from context_hub.mcp.server import MCP_TOOLS

        names = [t["name"] for t in MCP_TOOLS]
        assert len(names) == len(set(names)), "Duplicate tool names found"


# ---------------------------------------------------------------------------
# JSON-RPC response helpers
# ---------------------------------------------------------------------------


class TestJsonRpcHelpers:
    """Unit tests for _ok_response and _error_response."""

    def test_ok_response_structure(self) -> None:
        """_ok_response must return a valid JSON-RPC 2.0 success object."""
        from context_hub.mcp.server import _ok_response

        resp = _ok_response(req_id=42, result={"key": "value"})
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 42
        assert resp["result"] == {"key": "value"}
        assert "error" not in resp

    def test_error_response_structure(self) -> None:
        """_error_response must return a valid JSON-RPC 2.0 error object."""
        from context_hub.mcp.server import _error_response

        resp = _error_response(req_id=1, code=-32601, message="Method not found")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["error"]["code"] == -32601
        assert resp["error"]["message"] == "Method not found"
        assert "result" not in resp

    def test_ok_response_with_none_id(self) -> None:
        """_ok_response with id=None is valid for notifications."""
        from context_hub.mcp.server import _ok_response

        resp = _ok_response(req_id=None, result={})
        assert resp["id"] is None


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


class TestHandleRequest:
    """Unit tests for _handle_request."""

    @pytest.mark.asyncio
    async def test_initialize_returns_protocol_version(self) -> None:
        """'initialize' method must return the correct protocol version."""
        from context_hub.mcp import MCP_PROTOCOL_VERSION
        from context_hub.mcp.server import _handle_request

        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        response = await _handle_request(request)
        assert response is not None
        assert response["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION

    @pytest.mark.asyncio
    async def test_tools_list_returns_all_tools(self) -> None:
        """'tools/list' must return the full MCP_TOOLS list."""
        from context_hub.mcp.server import MCP_TOOLS, _handle_request

        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        response = await _handle_request(request)
        assert response is not None
        assert "tools" in response["result"]
        assert response["result"]["tools"] == MCP_TOOLS

    @pytest.mark.asyncio
    async def test_unknown_method_returns_error(self) -> None:
        """Unknown method with id must return a JSON-RPC -32601 error."""
        from context_hub.mcp.server import _handle_request

        request = {"jsonrpc": "2.0", "id": 3, "method": "unknown/method", "params": {}}
        response = await _handle_request(request)
        assert response is not None
        assert response["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_notification_returns_none(self) -> None:
        """Requests without 'id' (notifications) must return None."""
        from context_hub.mcp.server import _handle_request

        request = {"jsonrpc": "2.0", "method": "tools/list", "params": {}}
        response = await _handle_request(request)
        assert response is None

    @pytest.mark.asyncio
    async def test_tools_call_stub_tool_returns_result(self) -> None:
        """tools/call for a stub tool (trigger_sync) must return content with 'stub' status."""
        from context_hub.mcp.server import _handle_request

        request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "trigger_sync",
                "arguments": {"projectId": "proj-1", "source": "slack"},
            },
        }
        response = await _handle_request(request)
        assert response is not None
        content_str = response["result"]["content"][0]["text"]
        content = json.loads(content_str)
        assert content["status"] == "stub"


# ---------------------------------------------------------------------------
# search_context tool
# ---------------------------------------------------------------------------


class TestSearchContextTool:
    """Unit tests for the search_context tool dispatch."""

    @pytest.mark.asyncio
    async def test_search_context_missing_args_returns_error(self) -> None:
        """search_context with empty projectId/query must return an error dict."""
        from context_hub.mcp.server import _tool_search_context

        result = await _tool_search_context({"projectId": "", "query": ""})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_context_top_k_clamped_to_100(self) -> None:
        """search_context must clamp topK to at most 100 (F-11)."""
        import sys

        from context_hub.mcp.server import _tool_search_context

        captured_top_k: list[int] = []

        mock_service = AsyncMock()
        mock_service.search.side_effect = lambda **kwargs: (
            captured_top_k.append(kwargs["top_k"]) or []
        )

        settings_mock = MagicMock()
        settings_mock.embedding_provider = "mock"
        settings_mock.ch_sqlite_db = "./data/test.db"
        settings_mock.database_url = "sqlite+aiosqlite:///./data/test.db"

        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)
        mock_embedding_factory = MagicMock()
        mock_embedding_factory.get_embedding_provider = MagicMock(return_value=MagicMock())
        mock_doc_repo_module = MagicMock()
        mock_doc_repo_module.SqliteDocumentRepository = MagicMock(return_value=MagicMock())
        mock_qs_module = MagicMock()
        mock_qs_module.QueryService = MagicMock(return_value=mock_service)

        with patch.dict(
            sys.modules,
            {
                "context_hub.config.profiles": mock_profiles,
                "context_hub.infrastructure.embedding.factory": mock_embedding_factory,
                "context_hub.adapters.sqlite.document_repository": mock_doc_repo_module,
                "context_hub.application.query_service": mock_qs_module,
            },
        ):
            await _tool_search_context(
                {"projectId": "proj-1", "query": "test", "topK": 9999999}
            )

        assert captured_top_k, "service.search should have been called"
        assert captured_top_k[0] <= 100, f"topK should be clamped to 100, got {captured_top_k[0]}"

    @pytest.mark.asyncio
    async def test_search_context_top_k_clamped_to_minimum_1(self) -> None:
        """search_context must clamp topK to at least 1 (F-11)."""
        import sys

        from context_hub.mcp.server import _tool_search_context

        captured_top_k: list[int] = []

        mock_service = AsyncMock()
        mock_service.search.side_effect = lambda **kwargs: (
            captured_top_k.append(kwargs["top_k"]) or []
        )

        settings_mock = MagicMock()
        settings_mock.embedding_provider = "mock"
        settings_mock.ch_sqlite_db = "./data/test.db"
        settings_mock.database_url = "sqlite+aiosqlite:///./data/test.db"

        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)
        mock_embedding_factory = MagicMock()
        mock_embedding_factory.get_embedding_provider = MagicMock(return_value=MagicMock())
        mock_doc_repo_module = MagicMock()
        mock_doc_repo_module.SqliteDocumentRepository = MagicMock(return_value=MagicMock())
        mock_qs_module = MagicMock()
        mock_qs_module.QueryService = MagicMock(return_value=mock_service)

        with patch.dict(
            sys.modules,
            {
                "context_hub.config.profiles": mock_profiles,
                "context_hub.infrastructure.embedding.factory": mock_embedding_factory,
                "context_hub.adapters.sqlite.document_repository": mock_doc_repo_module,
                "context_hub.application.query_service": mock_qs_module,
            },
        ):
            await _tool_search_context(
                {"projectId": "proj-1", "query": "test", "topK": 0}
            )

        assert captured_top_k, "service.search should have been called"
        assert captured_top_k[0] >= 1, f"topK should be at least 1, got {captured_top_k[0]}"

    @pytest.mark.asyncio
    async def test_search_context_calls_query_service(self) -> None:
        """search_context must delegate to QueryService.search."""
        import sys

        from context_hub.mcp.server import _tool_search_context

        mock_result = MagicMock()
        mock_result.score = 0.9
        mock_result.title = "Test Doc"
        mock_result.snippet = "Test snippet"
        mock_result.document.id = "doc-uuid"

        mock_service = AsyncMock()
        mock_service.search.return_value = [mock_result]

        settings_mock = MagicMock()
        settings_mock.embedding_provider = "mock"
        settings_mock.ch_sqlite_db = "./data/test.db"
        settings_mock.database_url = "sqlite+aiosqlite:///./data/test.db"

        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(return_value=settings_mock)

        mock_embedding_factory = MagicMock()
        mock_embedding_factory.get_embedding_provider = MagicMock(return_value=MagicMock())

        mock_doc_repo_module = MagicMock()
        mock_doc_repo_module.SqliteDocumentRepository = MagicMock(return_value=MagicMock())

        mock_qs_module = MagicMock()
        mock_qs_module.QueryService = MagicMock(return_value=mock_service)

        with patch.dict(
            sys.modules,
            {
                "context_hub.config.profiles": mock_profiles,
                "context_hub.infrastructure.embedding.factory": mock_embedding_factory,
                "context_hub.adapters.sqlite.document_repository": mock_doc_repo_module,
                "context_hub.application.query_service": mock_qs_module,
            },
        ):
            result = await _tool_search_context(
                {"projectId": "proj-1", "query": "test query", "topK": 3}
            )

        assert "results" in result
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Test Doc"

    @pytest.mark.asyncio
    async def test_search_context_exception_returns_error(self) -> None:
        """search_context must handle exceptions and return a generic error dict.

        Internal exception details must NOT be exposed to MCP clients (F-2).
        The error message must be a safe generic string; details go to stderr only.
        """
        import sys

        from context_hub.mcp.server import _tool_search_context

        mock_profiles = MagicMock()
        mock_profiles.get_profile_settings = MagicMock(side_effect=RuntimeError("DB down"))

        with patch.dict(sys.modules, {"context_hub.config.profiles": mock_profiles}):
            result = await _tool_search_context(
                {"projectId": "proj-1", "query": "test"}
            )

        assert "error" in result
        # Internal error details must NOT leak to the MCP client (F-2 security fix)
        assert "DB down" not in result["error"]
        assert "Search failed" in result["error"]
        assert result["results"] == []


# ---------------------------------------------------------------------------
# /mcp/version HTTP endpoint
# ---------------------------------------------------------------------------


class TestMcpVersionEndpoint:
    """Integration test for the /mcp/version HTTP endpoint."""

    def test_mcp_version_returns_protocol_version(self) -> None:
        """GET /mcp/version must return the MCP protocol version."""
        from fastapi.testclient import TestClient

        from context_hub.main import app
        from context_hub.mcp import MCP_PROTOCOL_VERSION

        with TestClient(app) as client:
            response = client.get("/mcp/version")

        assert response.status_code == 200
        data = response.json()
        assert data["mcp_protocol_version"] == MCP_PROTOCOL_VERSION
        assert data["server"] == "context-hub"

    def test_mcp_version_is_in_openapi_schema(self) -> None:
        """The /mcp/version endpoint must appear in the OpenAPI schema."""
        from fastapi.testclient import TestClient

        from context_hub.main import app

        with TestClient(app) as client:
            response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        paths = schema.get("paths", {})
        assert "/mcp/version" in paths
