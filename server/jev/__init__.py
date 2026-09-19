"""Typed decisions backed by TypeSafe's System One model (Jev).

Optional layer: without ``TYPESAFE_API_KEY`` every entry point here returns an
"undecided"/"allow" result and the rest of the server behaves exactly as it did
before. See ``server/jev/questions.py`` for the questions asked and
``server/jev/thresholds.py`` for the thresholds they are judged against.
"""

from __future__ import annotations

from .client import close_client, is_enabled
from .decision_log import get_decision_log
from .decisions import (
    ALLOW,
    HOLD,
    QUARANTINE,
    SKIP,
    STEER,
    SURFACE,
    UNDECIDED,
    WARN,
    EmailScreening,
    SearchFilter,
    ToolCallReview,
    filter_search_results,
    record_screening,
    review_tool_call,
    screen_email,
)

__all__ = [
    "ALLOW",
    "EmailScreening",
    "HOLD",
    "QUARANTINE",
    "SKIP",
    "STEER",
    "SURFACE",
    "SearchFilter",
    "ToolCallReview",
    "UNDECIDED",
    "WARN",
    "close_client",
    "filter_search_results",
    "get_decision_log",
    "is_enabled",
    "record_screening",
    "review_tool_call",
    "screen_email",
]
