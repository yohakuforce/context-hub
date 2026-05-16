"""Configuration package for Context-Hub.

Exports:
- ProfileSettings: Pydantic BaseSettings with profile-aware defaults.
- get_profile_settings: Factory that returns settings for a given profile.
- settings: Module-level singleton (re-exported from context_hub.config.settings for
  backwards compatibility with callers that use ``from context_hub.config import settings``).
"""

from context_hub.config.profiles import ProfileSettings, get_profile_settings

# Re-export the legacy module-level singleton so that existing code using
# ``from context_hub.config import settings`` continues to work without changes.
from context_hub.config.settings import settings  # noqa: F401

__all__ = ["ProfileSettings", "get_profile_settings", "settings"]
