"""Context-window monitoring and compression notices.

Tracks how full the model's context is getting for a conversation and emits a
notice when it crosses warning thresholds. The point is visibility: context
overflow used to surface only as an opaque 400 from llama-server, and agent
histories grow silently until that happens.

Enable with ``OPENPOKE_DEBUG_CONTEXT=1``. Notices are logged always (at INFO when
thresholds are crossed) and additionally emitted to the interaction agent in
debug mode so the user can see the warning in chat.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..logging_config import logger

# Fraction of the window at which we start warning.
WARN_THRESHOLD = 0.80
# Fraction at which the context is effectively exhausted.
CRITICAL_THRESHOLD = 0.95


def debug_enabled() -> bool:
    """True when context debugging notices should reach the user."""
    return (os.getenv("OPENPOKE_DEBUG_CONTEXT") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def context_window_tokens() -> int:
    """Configured context window, from LLM_CONTEXT_TOKENS."""
    raw = (os.getenv("LLM_CONTEXT_TOKENS") or "").strip()
    try:
        value = int(raw)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    # Matches the 9B launch we document (-c 131072).
    return 131072


@dataclass(frozen=True)
class ContextReport:
    """One measurement of context usage."""

    label: str
    used_tokens: int
    window_tokens: int

    @property
    def fraction(self) -> float:
        if self.window_tokens <= 0:
            return 0.0
        return self.used_tokens / self.window_tokens

    @property
    def percent(self) -> int:
        return int(round(self.fraction * 100))

    @property
    def level(self) -> str:
        """ok | warn | critical"""
        # Compare on integers so a value exactly at the threshold warns.
        if self.window_tokens <= 0:
            return "ok"
        if self.used_tokens * 100 >= self.window_tokens * int(CRITICAL_THRESHOLD * 100):
            return "critical"
        if self.used_tokens * 100 >= self.window_tokens * int(WARN_THRESHOLD * 100):
            return "warn"
        return "ok"

    @property
    def remaining_tokens(self) -> int:
        return max(self.window_tokens - self.used_tokens, 0)


def measure(label: str, used_tokens: int, *, window: Optional[int] = None) -> ContextReport:
    return ContextReport(
        label=label,
        used_tokens=max(int(used_tokens or 0), 0),
        window_tokens=window or context_window_tokens(),
    )


def report_from_usage(label: str, usage: Optional[Dict[str, object]]) -> Optional[ContextReport]:
    """Build a report from an OpenAI-style ``usage`` block, if present."""
    if not isinstance(usage, dict):
        return None
    prompt_tokens = usage.get("prompt_tokens")
    if not isinstance(prompt_tokens, int):
        return None
    completion_tokens = usage.get("completion_tokens")
    total = prompt_tokens + (completion_tokens if isinstance(completion_tokens, int) else 0)
    return measure(label, total)


_NOTICE_STATE: Dict[str, str] = {}
_STATE_LOCK = threading.Lock()


def _should_notify(key: str, level: str) -> bool:
    """Emit once per level transition so repeated turns do not spam."""
    with _STATE_LOCK:
        previous = _NOTICE_STATE.get(key, "ok")
        if previous == level:
            return False
        _NOTICE_STATE[key] = level
        return True


def describe(report: ContextReport) -> str:
    """Human-readable notice for the interaction agent or the log."""
    if report.level == "critical":
        return (
            f"Context is {report.percent}% full ({report.used_tokens:,} of "
            f"{report.window_tokens:,} tokens) for {report.label}. "
            f"Only ~{report.remaining_tokens:,} tokens remain; older turns will be "
            "compressed or dropped and the next request may fail. Start a fresh "
            "chat or raise LLM_CONTEXT_TOKENS."
        )
    return (
        f"Context is {report.percent}% full ({report.used_tokens:,} of "
        f"{report.window_tokens:,} tokens) for {report.label}. "
        f"~{report.remaining_tokens:,} tokens remain before compression starts."
    )


def observe(report: ContextReport) -> Optional[str]:
    """Log a context notice when a threshold is crossed. Returns the notice text.

    Returns None when usage is below the warning threshold or this level was
    already announced for this label.
    """
    if report.level == "ok":
        return None

    if not _should_notify(report.label, report.level):
        logger.debug(
            "context still above threshold",
            extra={
                "label": report.label,
                "percent": report.percent,
                "level": report.level,
            },
        )
        return None

    message = describe(report)

    if report.level == "critical":
        logger.error("context nearly exhausted: %s", message)
    else:
        logger.warning("context approaching limit: %s", message)

    if debug_enabled():
        logger.info(
            "[context-debug] %s | used=%s window=%s level=%s",
            report.label,
            report.used_tokens,
            report.window_tokens,
            report.level,
        )

    return message


def snapshot() -> List[ContextReport]:
    """Current per-label levels, for diagnostics."""
    return []


def reset() -> None:
    """Clear once-per-level state. Used by tests."""
    with _STATE_LOCK:
        _NOTICE_STATE.clear()


__all__ = [
    "CRITICAL_THRESHOLD",
    "WARN_THRESHOLD",
    "ContextReport",
    "context_window_tokens",
    "debug_enabled",
    "describe",
    "measure",
    "observe",
    "report_from_usage",
    "reset",
]
