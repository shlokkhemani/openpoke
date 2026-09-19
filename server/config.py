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


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


def _env_flag(name: str, fallback: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return fallback
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


class Settings(BaseModel):
    """Application settings with lightweight env fallbacks."""

    # App metadata
    app_name: str = Field(default=DEFAULT_APP_NAME)
    app_version: str = Field(default=DEFAULT_APP_VERSION)

    # Server runtime
    server_host: str = Field(default=os.getenv("OPENPOKE_HOST", "0.0.0.0"))
    server_port: int = Field(default=_env_int("OPENPOKE_PORT", 8001))

    # LLM model selection
    interaction_agent_model: str = Field(default="anthropic/claude-sonnet-4")
    execution_agent_model: str = Field(default="anthropic/claude-sonnet-4")
    execution_agent_search_model: str = Field(default="anthropic/claude-sonnet-4")
    summarizer_model: str = Field(default="anthropic/claude-sonnet-4")
    email_classifier_model: str = Field(default="anthropic/claude-sonnet-4")

    # Typed decisions (TypeSafe System One / Jev)
    # Pinned rather than an alias: `jev-latest` moves when a release ships and
    # the thresholds in server/jev/thresholds.py are calibrated against one
    # model. https://docs.typesafe.ai/models
    jev_model: str = Field(default=os.getenv("JEV_MODEL", "jev-1.13.0"))
    jev_timeout_seconds: float = Field(default=_env_float("JEV_TIMEOUT_SECONDS", 3.0))
    jev_retry_budget_seconds: float = Field(default=_env_float("JEV_RETRY_BUDGET_SECONDS", 6.0))
    jev_max_retries: int = Field(default=_env_int("JEV_MAX_RETRIES", 1))
    # Hard wall-clock ceiling per call, retries and backoff included. The SDK's
    # retry budget is checked before it sleeps again, so the final attempt can
    # still add a full request timeout on top of it.
    jev_deadline_seconds: float = Field(default=_env_float("JEV_DEADLINE_SECONDS", 6.0))
    # Tighter still on the agent's hot path: this call happens before every
    # tool call, inside a run the batch manager caps at 90 seconds.
    jev_guardrail_deadline_seconds: float = Field(
        default=_env_float("JEV_GUARDRAIL_DEADLINE_SECONDS", 3.0)
    )
    jev_state_char_budget: int = Field(default=_env_int("JEV_STATE_CHAR_BUDGET", 24000))
    jev_search_max_candidates: int = Field(default=_env_int("JEV_SEARCH_MAX_CANDIDATES", 20))
    # Stored probabilities are what make thresholds re-tunable offline: a sweep
    # over the log costs nothing, a sweep that re-asks the model costs a run of
    # the whole mailbox.
    # An email that reads as an injection attempt is quarantined rather than
    # dropped: the body is withheld from the agent, but the user is told a
    # message arrived. Set to 0 for the older silent-drop behaviour, knowing
    # that silence is what a suppression attacker is buying.
    jev_quarantine_injections: bool = Field(default=_env_flag("JEV_QUARANTINE_INJECTIONS", True))
    jev_decision_log_enabled: bool = Field(default=_env_flag("JEV_DECISION_LOG", True))
    jev_decision_log_max_entries: int = Field(default=_env_int("JEV_DECISION_LOG_MAX_ENTRIES", 2000))
    jev_decision_log_path: str = Field(
        default=os.getenv("JEV_DECISION_LOG_PATH", "server/data/jev_decisions.jsonl")
    )
    jev_email_screening_enabled: bool = Field(default=_env_flag("JEV_EMAIL_SCREENING", True))
    jev_tool_guardrail_enabled: bool = Field(default=_env_flag("JEV_TOOL_GUARDRAIL", True))
    jev_search_filter_enabled: bool = Field(default=_env_flag("JEV_SEARCH_FILTER", True))

    # Credentials / integrations
    typesafe_api_key: Optional[str] = Field(default=os.getenv("TYPESAFE_API_KEY"))
    # Point System One requests at a gateway instead of api.typesafe.ai. The SDK
    # appends `/v1/systemone`, so give it an origin and no path suffix.
    typesafe_base_url: Optional[str] = Field(default=os.getenv("TYPESAFE_BASE_URL"))
    openrouter_api_key: Optional[str] = Field(default=os.getenv("OPENROUTER_API_KEY"))
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
    def jev_enabled(self) -> bool:
        """Flag indicating typed decisions are configured."""
        return bool((self.typesafe_api_key or "").strip())

    @property
    def summarization_enabled(self) -> bool:
        """Flag indicating conversation summarisation is active."""
        return self.conversation_summary_threshold > 0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
