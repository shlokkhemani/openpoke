"""Cheap token estimation used for context budgeting.

A tokenizer-free heuristic (~4 characters per token) is deliberately used: it is
model-agnostic, costs nothing, and only has to be consistent, not exact. Budgets
are set with headroom to absorb the error.
"""

from __future__ import annotations

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def chars_for_tokens(tokens: int) -> int:
    return max(0, tokens) * CHARS_PER_TOKEN


__all__ = ["estimate_tokens", "chars_for_tokens", "CHARS_PER_TOKEN"]
