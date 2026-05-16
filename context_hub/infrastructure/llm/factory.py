"""LLM adapter factory.

Reads LLM_PROVIDER from the environment and returns the appropriate adapter.
Business logic NEVER imports adapters directly — always goes through this factory.

Supported providers (2026-05-15 policy: subscription AI only, zero pay-per-token):
  claude-code  — ClaudeCodeAdapter  (Claude Code CLI subprocess)
  codex        — CodexAdapter       (Codex CLI subprocess)
  ollama       — OllamaAdapter      (local Ollama HTTP server)
  mock         — MockLLMAdapter     (test / CI, no external calls)

REMOVED providers (deprecated — see individual adapter files for migration guide):
  claude  — was ClaudeAdapter (Anthropic API, pay-per-token)
  openai  — was OpenAIAdapter (OpenAI API, pay-per-token)
"""

from __future__ import annotations

from context_hub.infrastructure.llm.base import LLMAdapter
from context_hub.infrastructure.llm.mock_adapter import MockLLMAdapter


def create_llm_adapter(
    provider: str,
    claude_code_timeout: float | None = None,
    codex_timeout: float | None = None,
    ollama_base_url: str | None = None,
    ollama_model: str | None = None,
    # Legacy kwargs — accepted but raise informative errors
    anthropic_api_key: str | None = None,
    openai_api_key: str | None = None,
    claude_model: str | None = None,
) -> LLMAdapter:
    """Construct the appropriate LLM adapter based on the provider name.

    Args:
        provider: One of "claude-code", "codex", "ollama", "mock".
        claude_code_timeout: Subprocess timeout in seconds for claude-code.
        codex_timeout: Subprocess timeout in seconds for codex.
        ollama_base_url: Override Ollama server URL (default: http://localhost:11434).
        ollama_model: Override Ollama model name (default: llama3).
        anthropic_api_key: DEPRECATED — raises ValueError if provider is "claude".
        openai_api_key: DEPRECATED — raises ValueError if provider is "openai".
        claude_model: DEPRECATED parameter, ignored.

    Returns:
        An LLMAdapter instance ready for use.

    Raises:
        ValueError: If provider is unknown or a deprecated provider is requested.
    """
    if provider == "mock":
        return MockLLMAdapter()

    if provider == "claude-code":
        from context_hub.infrastructure.llm.claude_code_adapter import ClaudeCodeAdapter
        return ClaudeCodeAdapter(timeout_seconds=claude_code_timeout)

    if provider == "codex":
        from context_hub.infrastructure.llm.codex_adapter import CodexAdapter
        return CodexAdapter(timeout_seconds=codex_timeout)

    if provider == "ollama":
        from context_hub.infrastructure.llm.ollama_adapter import OllamaAdapter
        return OllamaAdapter(base_url=ollama_base_url, model=ollama_model)

    # Deprecated provider guard — give actionable error messages
    if provider == "claude":
        raise ValueError(
            "LLM_PROVIDER='claude' is deprecated (Anthropic API is pay-per-token). "
            "Use LLM_PROVIDER='claude-code' to call the Claude Code CLI instead."
        )

    if provider == "openai":
        raise ValueError(
            "LLM_PROVIDER='openai' is deprecated (OpenAI API is pay-per-token). "
            "Use LLM_PROVIDER='codex' (Codex CLI) or 'ollama' (local) instead."
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. "
        "Supported values: claude-code, codex, ollama, mock"
    )


def create_embedding_service(provider: str) -> "object":
    """Construct the appropriate embedding service.

    Args:
        provider: One of "bge-m3", "mock".

    Returns:
        An EmbeddingProvider instance.

    Raises:
        ValueError: If provider is unknown or deprecated.
    """
    if provider == "mock":
        from context_hub.infrastructure.llm.mock_adapter import MockEmbeddingService
        return MockEmbeddingService()

    if provider == "bge-m3":
        from context_hub.infrastructure.embedding.bge_m3_adapter import BGEM3EmbeddingAdapter
        return BGEM3EmbeddingAdapter()

    # Deprecated provider guard
    if provider in ("openai", "claude"):
        raise ValueError(
            f"Embedding provider '{provider}' is deprecated (pay-per-token API). "
            "Use EMBEDDING_PROVIDER='bge-m3' for local BGE-M3 embedding."
        )

    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER '{provider}'. "
        "Supported values: bge-m3, mock"
    )
