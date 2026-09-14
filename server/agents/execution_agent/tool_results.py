"""Compatibility shim — prefer `server.agents.execution_agent.context.results` and `server.context`."""

from ...context.digest import digest_many, digest_text
from ...context.overflow import RESULT_TOO_LARGE, is_context_overflow, terminal_overflow_message
from ...context.preview import preview_text
from .context.results import DIGEST_EMAIL_SCHEMA, READ_EMAIL_SCHEMA, ResultStore, resolve_body_from

__all__ = [
    "DIGEST_EMAIL_SCHEMA",
    "READ_EMAIL_SCHEMA",
    "RESULT_TOO_LARGE",
    "ResultStore",
    "digest_many",
    "digest_text",
    "is_context_overflow",
    "preview_text",
    "resolve_body_from",
    "terminal_overflow_message",
]
