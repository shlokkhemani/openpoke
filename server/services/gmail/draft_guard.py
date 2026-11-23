"""Tracks draft creation and explicit user approval before an email can be sent.

The system prompt tells the model to create a draft first and only send after the
user confirms. Nothing enforced that, so a single tool call could send mail with
no human in the loop. This module makes the rule structural:

* ``gmail_create_draft`` registers the draft id it actually created.
* The interaction agent records an approval only after the user asks to send.
* ``gmail_execute_draft`` refuses any draft that was not created here, and any
  draft the user has not approved.

State is process-local and resets on restart, which is deliberate: a restarted
process must not inherit a stale approval and send something unreviewed.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional, Set

_LOCK = threading.Lock()
# Draft ids created through gmail_create_draft in this process.
_CREATED_DRAFTS: Set[str] = set()
# Draft id -> the recipient the draft was addressed to (for approval messaging).
_DRAFT_RECIPIENTS: Dict[str, str] = {}
# Draft ids the user has explicitly approved for sending.
_APPROVED_DRAFTS: Set[str] = set()


def _normalized(draft_id: Optional[str]) -> str:
    return (draft_id or "").strip()


def _extract_draft_id(result: object) -> Optional[str]:
    """Pull a draft id out of a Composio response of varying shape."""

    def walk(node: object, depth: int = 0) -> Optional[str]:
        if depth > 6:
            return None
        if isinstance(node, dict):
            for key in ("draft_id", "draftId", "id", "message_id", "messageId"):
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in node.values():
                found = walk(value, depth + 1)
                if found:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = walk(value, depth + 1)
                if found:
                    return found
        return None

    return walk(result)


def register_created_draft(result: object, *, recipient: Optional[str] = None) -> Optional[str]:
    """Record that a draft now exists. Returns the draft id if one was found."""
    draft_id = _extract_draft_id(result)
    if not draft_id:
        return None
    with _LOCK:
        _CREATED_DRAFTS.add(draft_id)
        if recipient:
            _DRAFT_RECIPIENTS[draft_id] = recipient
        # A freshly created draft is never pre-approved.
        _APPROVED_DRAFTS.discard(draft_id)
    return draft_id


def approve_draft(draft_id: str) -> bool:
    """Mark a draft as approved to send. Returns False if it was never created."""
    key = _normalized(draft_id)
    if not key:
        return False
    with _LOCK:
        if key not in _CREATED_DRAFTS:
            return False
        _APPROVED_DRAFTS.add(key)
        return True


def is_approved(draft_id: str) -> bool:
    key = _normalized(draft_id)
    with _LOCK:
        return key in _APPROVED_DRAFTS


def was_created(draft_id: str) -> bool:
    key = _normalized(draft_id)
    with _LOCK:
        return key in _CREATED_DRAFTS


def check_send_allowed(draft_id: str) -> Optional[str]:
    """Return an error message when sending is not permitted, else None."""
    key = _normalized(draft_id)
    if not key:
        return "draft_id is required to send a draft."

    with _LOCK:
        created = key in _CREATED_DRAFTS
        approved = key in _APPROVED_DRAFTS

    if not created:
        return (
            "Refusing to send: this draft was not created in this session. "
            "Create the draft first, show it to the user, and only send after they confirm."
        )
    if not approved:
        return (
            "Refusing to send: the user has not approved this draft yet. "
            "Show the draft and wait for explicit confirmation before sending."
        )
    return None


def reset() -> None:
    """Clear all tracked state. Used by tests and on process restart."""
    with _LOCK:
        _CREATED_DRAFTS.clear()
        _DRAFT_RECIPIENTS.clear()
        _APPROVED_DRAFTS.clear()


__all__ = [
    "approve_draft",
    "check_send_allowed",
    "is_approved",
    "register_created_draft",
    "reset",
    "was_created",
]
