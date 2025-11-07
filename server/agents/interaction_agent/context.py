"""Context management for passing Telegram chat information through the call stack."""

from contextvars import ContextVar
from typing import Optional

# Context variable to store the current Telegram chat ID
_telegram_chat_id: ContextVar[Optional[str]] = ContextVar("telegram_chat_id", default=None)


def set_telegram_chat_id(chat_id: str) -> None:
    """Set the Telegram chat ID for the current async context."""
    _telegram_chat_id.set(chat_id)


def get_telegram_chat_id() -> Optional[str]:
    """Get the Telegram chat ID for the current async context."""
    return _telegram_chat_id.get()


def clear_telegram_chat_id() -> None:
    """Clear the Telegram chat ID from the current async context."""
    _telegram_chat_id.set(None)
