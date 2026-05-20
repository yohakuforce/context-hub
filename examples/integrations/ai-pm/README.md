# AI-PM Integration with Context-Hub

This guide explains how to connect an AI agent (Claude Desktop, Claude Code) to
Context-Hub via MCP (Model Context Protocol) for project-aware assistance.

## Overview

```
Claude Desktop / Claude Code
         |
         | MCP stdio (JSON-RPC 2.0)
         v
   context-hub serve --mcp-only
         |
         v
   Hybrid search (vector + keyword)
         |
         v
   Local SQLite / PostgreSQL
   (your project's context: Slack, Backlog, Redmine)
```

## Prerequisites

1. Context-Hub installed: `pipx install yohakuforce-context-hub`
2. At least one project set up: `context-hub init --profile personal`
3. Database migrated: `context-hub migrate`
4. (Optional) Context ingested: `context-hub ingest slack --mode mock`

## Claude Desktop Setup

1. Copy `mcp.json` from this directory into your Claude Desktop config:

   **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. Edit the config:
   - Set `CH_SQLITE_DB` to the absolute path of your database file
   - Note: `CONTEXT_HUB_API_KEY` is **not required** yet. MCP stdio auth is not
     enforced; the server runs localhost-only. Full auth is planned for a future release.

3. Restart Claude Desktop. Context-Hub should appear in the MCP tools panel.

## Claude Code Setup

Add to your project's `.claude/settings.json` or `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "context-hub": {
      "command": "context-hub",
      "args": ["serve", "--mcp-only"],
      "env": {
        "CH_PROFILE": "personal"
      }
    }
  }
}
```

> Note: `CONTEXT_HUB_API_KEY` is not required in v0.1.0. MCP stdio runs localhost-only
> without auth enforcement. Full authentication will be added in v0.2.0.

## Available MCP Tools

| Tool | Description |
|---|---|
| `search_context` | Hybrid vector + keyword search across project documents |
| `get_project_context` | Get project overview or full context summary |
| `get_issues` | List Backlog or Redmine issues |
| `get_issue_detail` | Get issue details including comments |
| `get_meeting` | Get meeting transcript and summary |
| `get_members` | Get project team members |
| `trigger_sync` | Trigger incremental sync for a data source |

Note: In v0.1, only `search_context` is fully implemented. Other tools return stub responses
and will be completed in v0.2.

## Verifying the Connection

Before connecting via MCP stdio, verify the server is accessible over HTTP:

```bash
# Start HTTP server
context-hub serve &

# Check MCP version compatibility
curl http://127.0.0.1:8000/mcp/version
# Expected: {"mcp_protocol_version":"2024-11-05","server":"context-hub","server_version":"0.1.0"}

# Stop
kill %1
```

## Example Prompts

Once connected, you can ask Claude:

- "What are the open issues in the current project?"
- "Summarise the last team meeting"
- "Search for context about the deployment checklist"
- "Who are the team members on this project?"

## Troubleshooting

**Claude Desktop does not show Context-Hub tools**
- Verify `context-hub` is in PATH: `which context-hub`
- Check Claude Desktop logs for MCP connection errors
- Note: `CONTEXT_HUB_API_KEY` is not required and not checked in v0.1.0

**`search_context` returns empty results**
- Run `context-hub migrate` to ensure the database schema is up to date
- Run `context-hub ingest slack --mode mock` to add test data
- Check that the project exists: `curl http://127.0.0.1:8000/api/v1/projects`

**Permission denied on `.env`**
- Run `context-hub init --profile personal --force` to regenerate with correct permissions
