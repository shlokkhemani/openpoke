"""`read_conversation` tool: read the user conversation on demand (problems-and-solutions §1)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from server.services.conversation import get_working_memory_log

MAX_ENTRIES = 30
_VISIBLE_TAGS = {"user_message": "user", "poke_reply": "poke"}

_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_conversation",
            "description": (
                "Read recent messages between the user and Poke. Use it when the request refers to something "
                "you don't have (\"him\", \"that one\", \"same as before\", names or dates without context), "
                "or before creating/changing anything that may depend on earlier conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "last_n": {
                        "type": "integer",
                        "description": f"How many recent messages to return (default 10, max {MAX_ENTRIES}).",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional keyword filter, e.g. a name or topic. Matching is case-insensitive.",
                    },
                    "include_summary": {
                        "type": "boolean",
                        "description": "Also return the rolling summary of older conversation (default false).",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    }
]


def get_schemas() -> List[Dict[str, Any]]:
    return _SCHEMAS


def read_conversation(
    last_n: Optional[int] = 10, query: Optional[str] = None, include_summary: Optional[bool] = False
) -> Dict[str, Any]:
    state = get_working_memory_log().load_summary_state()
    try:
        limit = max(1, min(int(last_n or 10), MAX_ENTRIES))
    except (TypeError, ValueError):
        limit = 10

    entries = [e for e in state.unsummarized_entries if e.tag in _VISIBLE_TAGS]
    needle = (query or "").strip().lower()
    if needle:
        terms = needle.split()
        entries = [e for e in entries if any(term in e.payload.lower() for term in terms)]

    messages = [
        {"from": _VISIBLE_TAGS[e.tag], "timestamp": e.timestamp, "text": e.payload}
        for e in entries[-limit:]
    ]
    result: Dict[str, Any] = {"messages": messages}
    if include_summary:
        result["summary"] = state.summary_text or ""
    return result


def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:  # noqa: ARG001
    return {"read_conversation": read_conversation}


__all__ = ["build_registry", "get_schemas", "read_conversation"]
