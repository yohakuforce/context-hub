"""DEPRECATED: Direct Anthropic API adapter.

This module is RETAINED for reference only and MUST NOT be used in production.

Reason for deprecation (2026-05-15):
  Context-Hub policy mandates zero usage of pay-per-token APIs.
  Anthropic Claude API is a metered service and violates the "subscription AI only"
  constraint defined in tech-stack.md Section 0-B.

  Use ClaudeCodeAdapter (claude_code_adapter.py) instead, which drives
  the Claude Code CLI (LLM_PROVIDER=claude-code) via subprocess — fully
  covered by the existing Claude subscription with no additional charges.

To remove this file: search for any remaining imports of ClaudeAdapter and
replace with ClaudeCodeAdapter, then delete this file.
"""

# NOTE: This file intentionally imports nothing and defines no classes.
# Keeping the file avoids a hard import error if any legacy code references it,
# while the module-level docstring documents the deprecation clearly.

raise ImportError(
    "ClaudeAdapter (direct Anthropic API) is deprecated. "
    "Set LLM_PROVIDER=claude-code and use ClaudeCodeAdapter instead. "
    "See src/infrastructure/llm/claude_code_adapter.py."
)
