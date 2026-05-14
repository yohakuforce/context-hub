"""Application configuration.

All config values come from environment variables (read via pydantic-settings).
Never hardcode secrets here.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    # --- LLM Provider ---
    llm_provider: str = "mock"   # mock | claude | openai
    anthropic_api_key: str | None = None
    claude_model: str = "claude-3-5-sonnet-20241022"
    openai_api_key: str | None = None

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


# Module-level singleton — imported by the rest of the app
settings = Settings()
