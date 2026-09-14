"""Typed context-overflow errors for the budgeted strategy."""

from __future__ import annotations

from typing import Any

RESULT_TOO_LARGE = "RESULT_TOO_LARGE"
CONTEXT_OVERFLOW_MARKERS = (
    "context window exceeded",
    "context_length",
    "maximum context length",
    "too many tokens",
    "prompt is too long",
    "harnesstokengate",
)


def is_context_overflow(error: Any) -> bool:
    text = str(error).lower()
    return any(m in text for m in CONTEXT_OVERFLOW_MARKERS)


def terminal_overflow_message(where: str, detail: str = "") -> str:
    """A tool/agent error the model must treat as final: retrying with a different query cannot help."""
    return (
        f"{RESULT_TOO_LARGE}: the {where} exceeded the model's context window. Do NOT retry the same operation "
        f"with a narrower query or a smaller max_results; the failure is about size, not about the query. "
        f"Report this back with what you have so far. {detail}"
    ).strip()


__all__ = ["RESULT_TOO_LARGE", "CONTEXT_OVERFLOW_MARKERS", "is_context_overflow", "terminal_overflow_message"]
