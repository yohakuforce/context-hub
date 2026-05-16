"""Legacy Settings singleton — backwards compatibility shim.

This module preserves the ``settings`` singleton that existing code imports
via ``from src.config import settings`` or ``from src.config.settings import settings``.

New code should prefer ``src.config.profiles.get_profile_settings()`` which
supports the 3-profile system (quickstart / personal / production).

LLM_PROVIDER values (2026-05-15 policy — subscription AI only, zero pay-per-token):
  claude-code  — ClaudeCodeAdapter (subprocess: `claude -p`)
  codex        — CodexAdapter (subprocess: `codex -q`)
  ollama       — OllamaAdapter (HTTP to local Ollama server)
  mock         — MockLLMAdapter (CI / key-free dev)

EMBEDDING_PROVIDER values:
  bge-m3  — BGEM3EmbeddingAdapter (local FlagEmbedding, 1024-dim)
  mock    — MockEmbeddingService (CI / key-free dev)
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings read from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = Field(default="insecure-dev-secret-change-in-production")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/context_hub"
    )

    # --- LLM Provider (subscription AI only) ---
    # Values: claude-code | codex | ollama | mock
    llm_provider: str = "mock"
    claude_code_timeout_seconds: float = 120.0
    codex_timeout_seconds: float = 120.0
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # --- Embedding Provider (local, zero cost) ---
    # Values: bge-m3 | mock
    embedding_provider: str = "mock"
    embedding_device: str = "cpu"   # cpu | cuda

    # --- Slack ---
    slack_bot_token: str | None = None

    # --- Backlog ---
    backlog_api_key: str | None = None
    backlog_space_key: str | None = None

    # --- Redmine ---
    redmine_api_key: str | None = None
    redmine_base_url: str | None = None

    # --- Whisper ---
    whisper_model: str = "medium"

    # --- Data paths (inside container) ---
    meetings_data_dir: str = "/app/data/meetings"
    documents_data_dir: str = "/app/data/documents"


# Module-level singleton — imported by the rest of the app.
settings = Settings()
