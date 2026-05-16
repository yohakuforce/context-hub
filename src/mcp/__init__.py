"""Context-Hub MCP package.

Exposes the MCP protocol version constant for compatibility checks.
"""

from __future__ import annotations

#: MCP Protocol Version supported by this server.
#: AI-PM (Claude Desktop / Claude Code) can use /mcp/version to verify compatibility.
MCP_PROTOCOL_VERSION: str = "2024-11-05"

__all__ = ["MCP_PROTOCOL_VERSION"]
