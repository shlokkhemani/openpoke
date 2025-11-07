"""Simplified configuration management."""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

# Load environment variables from .env file, overriding existing ones
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

logger = logging.getLogger(__name__)

DEFAULT_APP_NAME = "Alyn Server"
DEFAULT_APP_VERSION = "0.3.0"
DEFAULT_MODEL = "google/gemini-2.0-flash-exp:free"


def _env_int(name: str, fallback: int) -> int:
    """Get integer from environment variable with fallback.

    Args:
        name: Environment variable name
        fallback: Default value if variable is not set or invalid

    Returns:
        Integer value from environment or fallback
    """
    value = os.getenv(name)
    if value is None:
        return fallback

    try:
        return int(value)
    except (TypeError, ValueError) as e:
        logger.warning(
            "Failed to parse environment variable %s='%s' as integer: %s. Using fallback: %d",
            name, value, e, fallback
        )
        return fallback


class Settings(BaseModel):
    """Application settings with lightweight env fallbacks."""

    # App metadata
    app_name: str = Field(default=DEFAULT_APP_NAME)
    app_version: str = Field(default=DEFAULT_APP_VERSION)

    # Server runtime
    server_host: str = Field(default=os.getenv("OPENPOKE_HOST", "0.0.0.0"))
    server_port: int = Field(default=_env_int("OPENPOKE_PORT", 8001))

    # LLM model selection - single variable for all agents
    # Set ALYN_MODEL in Railway to change the model for all agents
    # Example: ALYN_MODEL=openai/gpt-4-turbo
    _alyn_model: str = os.getenv("ALYN_MODEL", DEFAULT_MODEL)

    interaction_agent_model: str = Field(default=_alyn_model)
    execution_agent_model: str = Field(default=_alyn_model)
    execution_agent_search_model: str = Field(default=_alyn_model)
    summarizer_model: str = Field(default=os.getenv("SUMMARIZER_MODEL", "google/gemini-2.0-flash-exp:free"))
    email_classifier_model: str = Field(default=_alyn_model)

    # Credentials / integrations
    openrouter_api_key: Optional[str] = Field(default=os.getenv("OPENROUTER_API_KEY"))
    composio_gmail_auth_config_id: Optional[str] = Field(default=os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID"))
    composio_calendar_auth_config_id: Optional[str] = Field(default=os.getenv("COMPOSIO_CALENDAR_AUTH_CONFIG_ID"))
    composio_api_key: Optional[str] = Field(default=os.getenv("COMPOSIO_API_KEY"))
    composio_exa_mcp_url: Optional[str] = Field(default=os.getenv("COMPOSIO_EXA_MCP_URL"))
    composio_exa_user_id: Optional[str] = Field(default=os.getenv("COMPOSIO_EXA_USER_ID"))
    composio_exa_tool_name: str = Field(default=os.getenv("COMPOSIO_EXA_TOOL_NAME", "search_web"))
    composio_google_super_user_id: Optional[str] = Field(default=os.getenv("COMPOSIO_GOOGLESUPER_USER_ID"))
    composio_google_super_connected_account_id: Optional[str] = Field(default=os.getenv("COMPOSIO_GOOGLESUPER_CONNECTED_ACCOUNT_ID"))
    composio_google_super_toolkit_slug: Optional[str] = Field(default=os.getenv("COMPOSIO_GOOGLESUPER_TOOLKIT_SLUG"))
    exa_api_key: Optional[str] = Field(default=os.getenv("EXA_API_KEY"))

    # HTTP behaviour
    cors_allow_origins_raw: str = Field(default=os.getenv("OPENPOKE_CORS_ALLOW_ORIGINS", "*"))
    enable_docs: bool = Field(default=os.getenv("OPENPOKE_ENABLE_DOCS", "1") != "0")
    docs_url: Optional[str] = Field(default=os.getenv("OPENPOKE_DOCS_URL", "/docs"))

    # Summarisation controls
    conversation_summary_threshold: int = Field(default=100)
    conversation_summary_tail_size: int = Field(default=10)

    # Duplicate detection controls
    duplicate_detection_cache_size: int = Field(default=_env_int("DUPLICATE_DETECTION_CACHE_SIZE", 100))
    duplicate_detection_time_window: float = Field(default=float(os.getenv("DUPLICATE_DETECTION_TIME_WINDOW", "60.0")))

    @model_validator(mode='after')
    def validate_required_config(self) -> 'Settings':
        """Validate that required configuration is present.

        Raises:
            ValueError: If required configuration is missing or invalid
        """
        if not self.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable is required but not set. "
                "Please set it in your .env file or environment."
            )

        if len(self.openrouter_api_key.strip()) == 0:
            raise ValueError(
                "OPENROUTER_API_KEY is set but empty. "
                "Please provide a valid API key."
            )

        return self

    @property
    def cors_allow_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_allow_origins_raw.strip() in {"", "*"}:
            return ["*"]
        return [origin.strip() for origin in self.cors_allow_origins_raw.split(",") if origin.strip()]

    @property
    def resolved_docs_url(self) -> Optional[str]:
        """Return documentation URL when docs are enabled."""
        return (self.docs_url or "/docs") if self.enable_docs else None

    @property
    def summarization_enabled(self) -> bool:
        """Flag indicating conversation summarisation is active."""
        return self.conversation_summary_threshold > 0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings: Singleton settings instance

    Raises:
        ValueError: If required configuration is invalid
    """
    return Settings()
