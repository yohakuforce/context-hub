"""DEPRECATED: OpenAI API adapter (text generation + embedding).

This module is RETAINED for reference only and MUST NOT be used in production.

Reason for deprecation (2026-05-15):
  Context-Hub policy mandates zero usage of pay-per-token APIs.
  OpenAI API (gpt-4o, text-embedding-3-small) is a metered service and
  violates the "subscription AI only" constraint in tech-stack.md Section 0-B.

  Embedding replacement: BGEM3EmbeddingAdapter (embedding/bge_m3_adapter.py),
  which runs BGE-M3 locally at zero cost.

  LLM replacement: CodexAdapter (codex_adapter.py) for Codex subscription users,
  or ClaudeCodeAdapter (claude_code_adapter.py) for Claude subscription users.

To remove this file: confirm no remaining imports of OpenAIAdapter /
OpenAIEmbeddingService, then delete this file.
"""

raise ImportError(
    "OpenAIAdapter and OpenAIEmbeddingService (pay-per-token API) are deprecated. "
    "Use BGEM3EmbeddingAdapter for embeddings and ClaudeCodeAdapter/CodexAdapter "
    "for LLM generation. See src/infrastructure/embedding/ and src/infrastructure/llm/."
)
