"""Legacy Settings singleton — backwards compatibility shim.

This module preserves the ``settings`` singleton that existing code imports
via ``from context_hub.config import settings`` or
``from context_hub.config.settings import settings``.

New code should prefer ``context_hub.config.profiles.get_profile_settings()`` which
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
        extra="ignore",
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

    # --- Gmail ---
    # OAuth2 credentials from Google Cloud Console (Gmail API enabled).
    # The token file is created automatically on first browser consent.
    # Install live deps with: pip install 'yohakuforce-context-hub[gmail]'
    gmail_credentials_file: str | None = None
    gmail_token_file: str | None = None
    # Gmail search query — defaults to a label-based opt-in so only explicitly
    # labelled mail is ingested. Override with any Gmail search syntax.
    gmail_query: str = "label:context-hub"

    # --- Whisper ---
    whisper_model: str = "medium"

    # --- Data paths (inside container) ---
    meetings_data_dir: str = "/app/data/meetings"
    documents_data_dir: str = "/app/data/documents"

    # --- Inbox folder watcher ---
    # When ch_inbox_dir is set, a background job scans
    #   <ch_inbox_dir>/{meeting,file,email}/**/*.{md,txt}
    # on the configured interval and upserts each file as a Document.
    # Leave None / empty to disable.
    ch_inbox_dir: str | None = None
    ch_inbox_poll_seconds: int = 60
    # Optional explicit project_id for the inbox watcher. When unset,
    # the watcher uses the sole project in the repo (Context-Hub is 1:1 with a project).
    ch_project_id: str | None = None


# Module-level singleton — imported by the rest of the app.
settings = Settings()
