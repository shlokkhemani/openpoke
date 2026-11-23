"""`report_status` tool: the execution agent keeps its roster record up to date (§3a/§3c)."""

from __future__ import annotations

from functools import partial
from typing import Any, Callable, Dict, List, Optional

from server.services.execution import get_agent_roster
from server.services.execution.roster import VALID_STATUSES

_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "report_status",
            "description": (
                "Update this task's status and one-line summary. Call it once per run, in the same step "
                "as your last action (alongside your final tool calls), not as a separate step."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": list(VALID_STATUSES),
                        "description": (
                            "active: still working. waiting_on_user: needs the user's input or confirmation. "
                            "waiting_on_external: waiting on something else (e.g. a scheduled reminder or a reply). "
                            "done: the goal is finished and nothing is pending. Never use done while this task "
                            "still owns active reminders."
                        ),
                    },
                    "summary": {
                        "type": "string",
                        "description": "One line describing the goal and its current state, e.g. 'Insurance quotes: comparison reminder set for the 14th.'",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key people, emails, thread or trigger IDs this task is about (optional).",
                    },
                },
                "required": ["status", "summary"],
                "additionalProperties": False,
            },
        },
    }
]


def get_schemas() -> List[Dict[str, Any]]:
    return _SCHEMAS


def _report_status(
    *, agent_name: str, status: str, summary: str, entities: Optional[List[str]] = None
) -> Dict[str, Any]:
    try:
        record = get_agent_roster().update_record(
            agent_name, status=status, summary=summary, entities=entities
        )
    except ValueError as exc:
        return {"error": str(exc)}
    return {"status": record.status, "summary": record.summary}


def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    return {"report_status": partial(_report_status, agent_name=agent_name)}


__all__ = ["build_registry", "get_schemas"]
