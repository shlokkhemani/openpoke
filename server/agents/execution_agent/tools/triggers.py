"""Trigger tool schemas and actions for the execution agent."""

from __future__ import annotations

import json
from functools import partial
from typing import Any, Callable, Dict, List, Optional

from server.services.execution import get_execution_agent_logs
from server.services.timezone_store import get_timezone_store
from server.services.triggers import TriggerRecord, get_trigger_service

_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "createTrigger",
            "description": "Create a reminder trigger for the current execution agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {
                        "type": "string",
                        "description": "Raw instruction text that should run when the trigger fires.",
                    },
                    "recurrence_rule": {
                        "type": "string",
                        "description": "iCalendar RRULE string describing how often to fire (optional).",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "ISO 8601 start time for the first firing. Defaults to now if omitted.",
                    },
                    "status": {
                        "type": "string",
                        "description": "Initial status; usually 'active' or 'paused'.",
                    },
                },
                "required": ["payload"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "updateTrigger",
            "description": "Update or pause an existing trigger owned by this execution agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trigger_id": {
                        "type": "integer",
                        "description": "Identifier returned when the trigger was created.",
                    },
                    "payload": {
                        "type": "string",
                        "description": "Replace the instruction payload (optional).",
                    },
                    "recurrence_rule": {
                        "type": "string",
                        "description": "New RRULE definition (optional).",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "New ISO 8601 start time for the schedule (optional).",
                    },
                    "status": {
                        "type": "string",
                        "description": "Set trigger status to 'active', 'paused', or 'completed'.",
                    },
                },
                "required": ["trigger_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listTriggers",
            "description": "List all triggers belonging to this execution agent.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]

_LOG_STORE = get_execution_agent_logs()
_TRIGGER_SERVICE = get_trigger_service()
_MAX_TRIGGER_EXPORT = 10


# Return trigger tool schemas
def get_schemas() -> List[Dict[str, Any]]:
    """Return trigger tool schemas."""

    return _SCHEMAS


# Convert TriggerRecord to dictionary payload for API responses
def _summarize_payload(payload: str, *, max_length: int = 160) -> str:
    """Condense a trigger payload to avoid bloating LLM prompts."""

    normalized = " ".join(payload.split())
    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 1].rstrip()}…"


def _trigger_record_to_payload(record: TriggerRecord) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": record.id,
        "payload_summary": _summarize_payload(record.payload),
        "status": record.status,
    }

    if record.next_trigger:
        payload["next_trigger"] = record.next_trigger

    if record.start_time:
        payload["start_time"] = record.start_time

    if record.recurrence_rule:
        payload["recurrence_rule"] = record.recurrence_rule

    if record.timezone:
        payload["timezone"] = record.timezone

    if record.last_error:
        payload["last_error"] = record.last_error

    return payload


# Create a new trigger for the specified execution agent
def _create_trigger_tool(
    *,
    agent_name: str,
    payload: str,
    recurrence_rule: Optional[str] = None,
    start_time: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    timezone_value = get_timezone_store().get_timezone()
    summary_args = {
        "recurrence_rule": recurrence_rule,
        "start_time": start_time,
        "timezone": timezone_value,
        "status": status,
    }
    try:
        record = _TRIGGER_SERVICE.create_trigger(
            agent_name=agent_name,
            payload=payload,
            recurrence_rule=recurrence_rule,
            start_time=start_time,
            timezone_name=timezone_value,
            status=status,
        )
    except Exception as exc:  # pragma: no cover - defensive
        _LOG_STORE.record_action(
            agent_name,
            description=f"createTrigger failed | details={json.dumps(summary_args, ensure_ascii=False)} | error={exc}",
        )
        return {"error": str(exc)}

    _LOG_STORE.record_action(
        agent_name,
        description=f"createTrigger succeeded | trigger_id={record.id}",
    )
    response = _trigger_record_to_payload(record)
    response["trigger_id"] = record.id
    return response


# Update or pause an existing trigger owned by this execution agent
def _update_trigger_tool(
    *,
    agent_name: str,
    trigger_id: Any,
    payload: Optional[str] = None,
    recurrence_rule: Optional[str] = None,
    start_time: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        trigger_id_int = int(trigger_id)
    except (TypeError, ValueError):
        return {"error": "trigger_id must be an integer"}

    try:
        timezone_value = get_timezone_store().get_timezone()
        record = _TRIGGER_SERVICE.update_trigger(
            trigger_id_int,
            agent_name=agent_name,
            payload=payload,
            recurrence_rule=recurrence_rule,
            start_time=start_time,
            timezone_name=timezone_value,
            status=status,
        )
    except Exception as exc:  # pragma: no cover - defensive
        _LOG_STORE.record_action(
            agent_name,
            description=f"updateTrigger failed | id={trigger_id_int} | error={exc}",
        )
        return {"error": str(exc)}

    if record is None:
        return {"error": f"Trigger {trigger_id_int} not found"}

    _LOG_STORE.record_action(
        agent_name,
        description=f"updateTrigger succeeded | trigger_id={trigger_id_int}",
    )
    response = _trigger_record_to_payload(record)
    response["trigger_id"] = record.id
    return response


# List all triggers belonging to this execution agent
def _list_triggers_tool(*, agent_name: str) -> Dict[str, Any]:
    try:
        records = _TRIGGER_SERVICE.list_triggers(agent_name=agent_name)
    except Exception as exc:  # pragma: no cover - defensive
        _LOG_STORE.record_action(
            agent_name,
            description=f"listTriggers failed | error={exc}",
        )
        return {"error": str(exc)}

    total_records = len(records)
    if total_records > _MAX_TRIGGER_EXPORT:
        records = records[:_MAX_TRIGGER_EXPORT]

    _LOG_STORE.record_action(
        agent_name,
        description=f"listTriggers succeeded | count={total_records} | returned={len(records)}",
    )
    summarized: List[Dict[str, Any]] = []
    for record in records:
        payload = _trigger_record_to_payload(record)
        summarized.append(payload)

    return {"triggers": summarized}


# Return trigger tool callables bound to a specific agent
def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    """Return trigger tool callables bound to a specific agent."""

    return {
        "createTrigger": partial(_create_trigger_tool, agent_name=agent_name),
        "updateTrigger": partial(_update_trigger_tool, agent_name=agent_name),
        "listTriggers": partial(_list_triggers_tool, agent_name=agent_name),
    }


__all__ = [
    "build_registry",
    "get_schemas",
]
