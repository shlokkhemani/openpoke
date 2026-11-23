"""Gmail-related service helpers."""

from .client import (
    disconnect_account,
    execute_gmail_tool,
    fetch_status,
    get_active_gmail_user_id,
    initiate_connect,
)
from . import draft_guard
from .importance_classifier import classify_email_importance
from .importance_watcher import ImportantEmailWatcher, get_important_email_watcher
from .processing import EmailTextCleaner, ProcessedEmail, parse_gmail_fetch_response
from .seen_store import GmailSeenStore

__all__ = [
    "execute_gmail_tool",
    "fetch_status",
    "initiate_connect",
    "disconnect_account",
    "get_active_gmail_user_id",
    "classify_email_importance",
    "draft_guard",
    "ImportantEmailWatcher",
    "get_important_email_watcher",
    "EmailTextCleaner",
    "ProcessedEmail",
    "parse_gmail_fetch_response",
    "GmailSeenStore",
]
