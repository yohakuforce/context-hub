"""LLM adapter factory.

Reads LLM_PROVIDER from the environment and returns the appropriate adapter.
Business logic NEVER imports adapters directly — always goes through this factory.
"""

from __future__ import annotations

from src.infrastructure.llm.base import LLMAdapter
from src.infrastructure.llm.mock_adapter import MockEmbeddingService, MockLLMAdapter


def create_llm_adapter(
    provider: str,
    anthropic_api_key: str | None = None,
    openai_api_key: str | None = None,
    claude_model: str = "claude-3-5-sonnet-20241022",
) -> LLMAdapter:
    """Construct the appropriate LLM adapter based on the provider name.

    Args:
        provider: One of "claude", "openai", "mock".
        anthropic_api_key: Required when provider="claude".
        openai_api_key: Required when provider="openai".
        claude_model: Model to use for Claude (default: claude-3-5-sonnet).

    Returns:
        An LLMAdapter instance ready for use.

    Raises:
        ValueError: If provider is unknown or required key is missing.
    """
    if provider == "mock":
        return MockLLMAdapter()

    if provider == "claude":
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for LLM_PROVIDER=claude")
        # Lazy import to avoid loading anthropic SDK when not needed
        from src.infrastructure.llm.claude_adapter import ClaudeAdapter

        return ClaudeAdapter(api_key=anthropic_api_key, model=claude_model)

    if provider == "openai":
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for LLM_PROVIDER=openai")
        from src.infrastructure.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(api_key=openai_api_key)

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. "
        "Supported values: claude, openai, mock"
    )


def create_embedding_service(
    provider: str,
    openai_api_key: str | None = None,
) -> "MockEmbeddingService":  # return type broadened to protocol when antigravity added
    """Construct the appropriate embedding service.

    Currently only OpenAI and mock are supported.
    """
    if provider == "mock":
        return MockEmbeddingService()

    if provider in ("claude", "openai"):
        if not openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for embedding regardless of LLM_PROVIDER. "
                "Set LLM_PROVIDER=mock to skip embedding."
            )
        from src.infrastructure.llm.openai_adapter import OpenAIEmbeddingService

        return OpenAIEmbeddingService(api_key=openai_api_key)  # type: ignore[return-value]

    raise ValueError(
        f"Unknown provider for embedding '{provider}'. "
        "Supported values: claude, openai, mock"
    )
