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

    # Credentials / integrations
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

    # Context management (interaction agent)
    # "legacy": whole history (or summary + full tail) is pasted into every prompt.
    # "budgeted": history is assembled newest-first within a token budget; oversized
    #             entries are previewed, older entries indexed, and the agent can fetch
    #             any of them on demand with the recall_history tool.
    context_strategy: str = Field(default=os.getenv("OPENPOKE_CONTEXT_STRATEGY", "legacy"))
    context_budget_tokens: int = Field(default=_env_int("OPENPOKE_CONTEXT_BUDGET_TOKENS", 24_000))
    context_entry_max_tokens: int = Field(default=_env_int("OPENPOKE_CONTEXT_ENTRY_MAX_TOKENS", 1_500))
    context_index_max_lines: int = Field(default=_env_int("OPENPOKE_CONTEXT_INDEX_MAX_LINES", 120))
    context_turn_max_tokens: int = Field(default=_env_int("OPENPOKE_CONTEXT_TURN_MAX_TOKENS", 6_000))
    roster_v2_enabled: bool = Field(default=os.getenv("OPENPOKE_ROSTER_V2", "1") not in ("0", "false", "False"))
    roster_inline_limit: int = Field(default=_env_int("OPENPOKE_ROSTER_INLINE_LIMIT", 12))
    recall_calls_per_turn: int = Field(default=_env_int("OPENPOKE_RECALL_CALLS_PER_TURN", 3))
    turn_tool_result_budget_tokens: int = Field(default=_env_int("OPENPOKE_TURN_TOOL_RESULT_BUDGET_TOKENS", 24_000))
    interaction_digest_enabled: bool = Field(default=os.getenv("OPENPOKE_INTERACTION_DIGEST", "1") not in ("0", "false", "False"))
    recall_max_tokens: int = Field(default=_env_int("OPENPOKE_RECALL_MAX_TOKENS", 6_000))
    # budgeted-only summariser controls: also trigger on tail size in tokens, and never
    # feed the summariser more than this many tokens of entries in one call.
    conversation_summary_token_threshold: int = Field(default=_env_int("OPENPOKE_SUMMARY_TOKEN_THRESHOLD", 40_000))
    summarizer_batch_max_tokens: int = Field(default=_env_int("OPENPOKE_SUMMARY_BATCH_MAX_TOKENS", 60_000))
    worker_history_budget_tokens: int = Field(default=_env_int("OPENPOKE_WORKER_HISTORY_BUDGET_TOKENS", 16_000))
    tool_result_max_tokens: int = Field(default=_env_int("OPENPOKE_TOOL_RESULT_MAX_TOKENS", 8_000))
    tool_result_email_tokens: int = Field(default=_env_int("OPENPOKE_TOOL_RESULT_EMAIL_TOKENS", 2_000))
    search_preview_tokens: int = Field(default=_env_int("OPENPOKE_SEARCH_PREVIEW_TOKENS", 400))
    digest_chunk_tokens: int = Field(default=_env_int("OPENPOKE_DIGEST_CHUNK_TOKENS", 12_000))
    digest_concurrency: int = Field(default=_env_int("OPENPOKE_DIGEST_CONCURRENCY", 8))
    digest_call_timeout_s: int = Field(default=_env_int("OPENPOKE_DIGEST_CALL_TIMEOUT_S", 45))
    read_email_pages_per_run: int = Field(default=_env_int("OPENPOKE_READ_EMAIL_PAGES_PER_RUN", 3))
    tool_result_run_budget_tokens: int = Field(default=_env_int("OPENPOKE_TOOL_RESULT_RUN_BUDGET_TOKENS", 32_000))
    search_max_iterations_budgeted: int = Field(default=_env_int("OPENPOKE_SEARCH_MAX_ITERATIONS_BUDGETED", 3))

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
    def budgeted_context(self) -> bool:
        """True when the token-budgeted context strategy is active."""
        return self.context_strategy.strip().lower() == "budgeted"

    @property
    def summarization_enabled(self) -> bool:
        """Flag indicating conversation summarisation is active."""
        return self.conversation_summary_threshold > 0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
