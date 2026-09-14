"""Budgeted-only execution agent tools (schemas + registry wiring)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from ..context.history import recall_worker_entries
from ..context.results import DIGEST_EMAIL_SCHEMA, READ_EMAIL_SCHEMA
from . import gmail_v2

RECALL_WORKER_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "recall_worker_history",
        "description": (
            "Fetch the full text of earlier entries from this agent's execution history that are shown only as "
            "index lines or truncated previews. Pass entry ids (preferred) or a short search query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entry_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Entry ids from the index or from truncated entries.",
                },
                "query": {
                    "type": "string",
                    "description": "Alternative to entry_ids: distinctive words or identifiers to search for.",
                },
                "limit": {"type": "integer", "description": "Max entries to return for a query (default 5)."},
                "offset_chars": {
                    "type": "integer",
                    "description": "For a single very large entry: character offset to continue reading from.",
                },
            },
            "additionalProperties": False,
        },
    },
}


def get_schemas() -> List[Dict[str, Any]]:
    """Return every schema available only under the budgeted strategy."""
    return [
        RECALL_WORKER_SCHEMA,
        *gmail_v2.get_schemas(),
        READ_EMAIL_SCHEMA,
        DIGEST_EMAIL_SCHEMA,
    ]


def extend_registry(registry: Dict[str, Callable[..., Any]], agent_name: str) -> None:
    def recall_worker_history(entry_ids=None, query=None, limit=5, offset_chars=0):
        return recall_worker_entries(
            agent_name, entry_ids=entry_ids, query=query, limit=limit, offset_chars=offset_chars
        )

    registry["recall_worker_history"] = recall_worker_history


__all__ = [
    "DIGEST_EMAIL_SCHEMA",
    "READ_EMAIL_SCHEMA",
    "RECALL_WORKER_SCHEMA",
    "extend_registry",
    "get_schemas",
]
