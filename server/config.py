"""Simplified configuration management."""

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


def _load_env_file() -> None:
    """Load .env from root directory if present."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, value = stripped.split("=", 1)
                key, value = key.strip(), value.strip().strip("'\"")
                if key and value and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


_load_env_file()


DEFAULT_APP_NAME = "OpenPoke Server"
DEFAULT_APP_VERSION = "0.3.0"

DEFAULT_LLM_BASE_URL = "http://127.0.0.1:8080/v1"
# The id llama-server exposes for models/Qwen3.5-9B-Q4_K_M.gguf
DEFAULT_LLM_MODEL = "Qwen3.5-9B-Q4_K_M"
DEFAULT_LLM_TIMEOUT_SECONDS = 300


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


def _env_optional(name: str) -> Optional[str]:
    """Read an optional string env var, treating blanks as unset."""
    value = (os.getenv(name) or "").strip()
    return value or None


class Settings(BaseModel):
    """Application settings with lightweight env fallbacks."""

    # App metadata
    app_name: str = Field(default=DEFAULT_APP_NAME)
    app_version: str = Field(default=DEFAULT_APP_VERSION)

    # Server runtime
    server_host: str = Field(default=os.getenv("OPENPOKE_HOST", "0.0.0.0"))
    server_port: int = Field(default=_env_int("OPENPOKE_PORT", 8001))

    # LLM endpoint (OpenAI-compatible; defaults to a local llama-server).
    # These read the environment per instantiation so tests and reloads see
    # the current values rather than whatever was set at import time.
    llm_base_url: str = Field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL)
    )
    llm_api_key: Optional[str] = Field(default_factory=lambda: _env_optional("LLM_API_KEY"))
    llm_timeout_seconds: int = Field(
        default_factory=lambda: _env_int("LLM_TIMEOUT", DEFAULT_LLM_TIMEOUT_SECONDS)
    )
    llm_model: str = Field(
        default_factory=lambda: (
            os.getenv("LLM_MODEL")
            or os.getenv("OPENPOKE_MODEL")
            or DEFAULT_LLM_MODEL
        )
    )

    # Credentials / integrations
    composio_gmail_auth_config_id: Optional[str] = Field(default=os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID"))
    composio_api_key: Optional[str] = Field(default=os.getenv("COMPOSIO_API_KEY"))

    # HTTP behaviour
    cors_allow_origins_raw: str = Field(default=os.getenv("OPENPOKE_CORS_ALLOW_ORIGINS", "*"))
    enable_docs: bool = Field(default=os.getenv("OPENPOKE_ENABLE_DOCS", "1") != "0")
    docs_url: Optional[str] = Field(default=os.getenv("OPENPOKE_DOCS_URL", "/docs"))

    # Summarisation controls
    conversation_summary_threshold: int = Field(default=100)
    conversation_summary_tail_size: int = Field(default=10)

    @property
    def interaction_agent_model(self) -> str:
        """Model for the interaction agent."""
        return self.llm_model

    @property
    def execution_agent_model(self) -> str:
        """Model for execution agents."""
        return self.llm_model

    @property
    def execution_agent_search_model(self) -> str:
        """Model for the email search orchestrator."""
        return self.llm_model

    @property
    def summarizer_model(self) -> str:
        """Model for conversation summarization."""
        return self.llm_model

    @property
    def email_classifier_model(self) -> str:
        """Model for the important-email classifier."""
        return self.llm_model

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
    """Get cached settings instance."""
    return Settings()
