"""Shared budgeted-context primitives (digest, overflow, preview).

Agent-specific assembly lives under each agent's `context/` package.
"""

from .digest import digest_many, digest_text
from .overflow import RESULT_TOO_LARGE, is_context_overflow, terminal_overflow_message
from .preview import preview_text

__all__ = [
    "RESULT_TOO_LARGE",
    "digest_many",
    "digest_text",
    "is_context_overflow",
    "preview_text",
    "terminal_overflow_message",
]
