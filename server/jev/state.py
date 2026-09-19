"""Builders for the ``state`` payloads handed to Jev.

Two documented constraints shape everything here:

* Accuracy falls as the state grows with content unrelated to the decision, so
  filtering happens in Python before the request, not in the instructions.
  https://docs.typesafe.ai/model-jaggedness/jev-1.13
* A request allows 32k tokens for ``state`` plus the longest question, inside a
  64k total. https://docs.typesafe.ai/models

Named object fields are preferred over one flattened string: they keep the
relationships between parts explicit. https://docs.typesafe.ai/concepts/state
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..config import get_settings


# Cut a string to a character budget, marking where it was cut
def clip(text: Optional[str], limit: int) -> str:
    """Return ``text`` truncated to ``limit`` characters."""

    if not text:
        return ""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    marker = "\n[truncated]"
    if limit <= len(marker):
        return text[:limit]
    return text[: limit - len(marker)].rstrip() + marker


# Resolve the per-request character budget for email and transcript bodies
def body_budget() -> int:
    """Return the configured character budget for a single body field."""

    return max(0, get_settings().jev_state_char_budget)


# Describe one incoming email for the screening questions
def email_state(
    *,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    labels: Sequence[str] = (),
    has_attachments: bool = False,
    attachment_filenames: Sequence[str] = (),
) -> Dict[str, Any]:
    """Build the state object for :data:`server.jev.questions.EMAIL_QUESTIONS`.

    The received timestamp is deliberately **omitted**. jev-1.13 reads dates as
    text rather than as ordered quantities, so age and deadline reasoning is
    done in Python by the caller.
    https://docs.typesafe.ai/model-jaggedness/jev-1.13
    """

    return {
        "from": sender or "",
        "to": recipient or "",
        "subject": subject or "",
        "labels": list(labels),
        "has_attachments": bool(has_attachments),
        "attachment_filenames": list(attachment_filenames),
        "body": clip(body, body_budget()),
    }


# Describe a pending tool call for the guardrail questions
def tool_call_state(
    *,
    assignment: str,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the state object for :data:`server.jev.questions.TOOL_QUESTIONS`."""

    budget = body_budget()
    clipped_arguments: Dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            clipped_arguments[key] = clip(value, budget)
        else:
            clipped_arguments[key] = value

    return {
        "assignment": clip(assignment, budget),
        "tool": {"name": tool_name, "arguments": clipped_arguments},
    }


# Describe a search request and its candidate results for the relevance filter
def search_candidate_limit() -> int:
    """Return the most candidates a single relevance call may carry."""

    return max(1, get_settings().jev_search_max_candidates)


def search_state(
    *,
    request: str,
    candidates: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build the state object for the batched search relevance questions.

    ``candidates`` must be in the same order as the questions built by
    :func:`server.jev.questions.search_relevance_questions`, because the
    questions address entries by index.
    """

    budget = body_budget()
    # The number of selected ids is chosen by an LLM, so the state size has to
    # be capped here rather than trusted: a request allows 32k tokens for the
    # state plus the longest question. https://docs.typesafe.ai/models
    limited = list(candidates)[: max(1, get_settings().jev_search_max_candidates)]
    per_candidate = budget // max(1, len(limited)) if limited else budget

    trimmed: List[Dict[str, Any]] = []
    for candidate in limited:
        trimmed.append(
            {
                "index": len(trimmed),
                "from": str(candidate.get("from") or candidate.get("sender") or ""),
                "subject": str(candidate.get("subject") or ""),
                "body": clip(str(candidate.get("body") or candidate.get("clean_text") or ""), per_candidate),
            }
        )

    return {"request": clip(request, budget), "candidates": trimmed}


__all__ = [
    "body_budget",
    "clip",
    "email_state",
    "search_candidate_limit",
    "search_state",
    "tool_call_state",
]
