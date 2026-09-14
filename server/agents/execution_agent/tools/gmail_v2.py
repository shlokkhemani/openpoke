"""Versioned Gmail tools for the budgeted context strategy.

`gmail_create_draft_v2` adds `body_from`: the draft body is resolved server-side from a stored source
(a conversation entry id, or an email message id from this run's search results) so long text never
passes through a model. The legacy `gmail_create_draft` is untouched; this module is registered only
when the budgeted strategy is active. Execution is intercepted by the runtime (it owns the run store).
"""

from __future__ import annotations

from typing import Any, Dict, List

CREATE_DRAFT_V2_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "gmail_create_draft_v2",
        "description": (
            "Create a Gmail draft whose body comes from a stored source by reference (body_from), optionally wrapped "
            "with a short prefix/suffix, instead of pasting the text yourself. Use this whenever the instructions name "
            "a conversation entry id or a message id as the body, or the body is longer than a few paragraphs. "
            "The full text is copied server-side; you never need to read it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recipient_email": {"type": "string"},
                "subject": {"type": "string"},
                "body_from": {
                    "type": "object",
                    "description": "Where the body text lives.",
                    "properties": {
                        "source": {"type": "string", "enum": ["conversation", "email"],
                                   "description": "'conversation' = a conversation entry id; 'email' = a message id from this run's search results."},
                        "id": {"type": "string", "description": "Entry id or message id."},
                        "start_chars": {"type": "integer", "description": "Optional start offset within the source text."},
                        "end_chars": {"type": "integer", "description": "Optional end offset within the source text."},
                    },
                    "required": ["source", "id"],
                    "additionalProperties": False,
                },
                "body_prefix": {"type": "string", "description": "Optional short text placed before the referenced body (e.g. a greeting line)."},
                "body_suffix": {"type": "string", "description": "Optional short text placed after it (e.g. a sign-off)."},
                "cc": {"type": "array", "items": {"type": "string"}},
                "bcc": {"type": "array", "items": {"type": "string"}},
                "thread_id": {"type": "string", "description": "Existing thread id when replying on a thread."},
            },
            "required": ["recipient_email", "subject", "body_from"],
            "additionalProperties": False,
        },
    },
}


def get_schemas() -> List[Dict[str, Any]]:
    return [CREATE_DRAFT_V2_SCHEMA]


__all__ = ["CREATE_DRAFT_V2_SCHEMA", "get_schemas"]
