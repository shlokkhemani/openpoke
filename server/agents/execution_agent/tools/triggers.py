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


# Return trigger tool schemas
def get_schemas() -> List[Dict[str, Any]]:
    """Return trigger tool schemas."""

    return _SCHEMAS


# Convert TriggerRecord to dictionary payload for API responses
def _trigger_record_to_payload(record: TriggerRecord) -> Dict[str, Any]:
    return {
        "id": record.id,
        # Which identity owns this trigger: the calling agent, or "Reminders".
        "owner": record.agent_name,
        "payload": record.payload,
        "start_time": record.start_time,
        "next_trigger": record.next_trigger,
        "recurrence_rule": record.recurrence_rule,
        "timezone": record.timezone,
        "status": record.status,
        "last_error": record.last_error,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


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
    return {
        "trigger_id": record.id,
        "status": record.status,
        "next_trigger": record.next_trigger,
        "start_time": record.start_time,
        "timezone": record.timezone,
        "recurrence_rule": record.recurrence_rule,
    }


# Update or pause a trigger this agent owns, or a shared reminder
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

    owner = _resolve_trigger_owner(trigger_id_int, agent_name=agent_name)
    if owner is None:
        return {"error": f"Trigger {trigger_id_int} not found"}

    try:
        timezone_value = get_timezone_store().get_timezone()
        record = _TRIGGER_SERVICE.update_trigger(
            trigger_id_int,
            agent_name=owner,
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
    return {
        "trigger_id": record.id,
        "status": record.status,
        "next_trigger": record.next_trigger,
        "start_time": record.start_time,
        "timezone": record.timezone,
        "recurrence_rule": record.recurrence_rule,
        "last_error": record.last_error,
    }


# List triggers owned by this agent plus the shared reminders it can manage
def _list_triggers_tool(*, agent_name: str) -> Dict[str, Any]:
    # Imported lazily: the reminders package depends on this module at import time.
    from server.services.reminders import REMINDER_AGENT_NAME, is_reminder_agent

    try:
        # Reminders are created under the reserved identity, so an agent must
        # also see those or it would be told it has no reminders it just made.
        owners = [agent_name]
        if not is_reminder_agent(agent_name):
            owners.append(REMINDER_AGENT_NAME)

        records: List[TriggerRecord] = []
        seen: set[int] = set()
        for owner in owners:
            for record in _TRIGGER_SERVICE.list_triggers(agent_name=owner):
                if record.id in seen:
                    continue
                seen.add(record.id)
                records.append(record)
    except Exception as exc:  # pragma: no cover - defensive
        _LOG_STORE.record_action(
            agent_name,
            description=f"listTriggers failed | error={exc}",
        )
        return {"error": str(exc)}

    _LOG_STORE.record_action(
        agent_name,
        description=f"listTriggers succeeded | count={len(records)}",
    )
    return {"triggers": [_trigger_record_to_payload(record) for record in records]}


# Route new reminders to the single reserved reminder identity.
def _default_reminder_owner(agent_name: str) -> str:
    """Return the identity new reminders are stored under.

    Previously every reminder was created against the calling execution agent,
    so N reminders meant N roster entries competing for prompt slots. Sending
    them all to one reserved identity removes that competition.
    """
    from server.services.reminders import REMINDER_AGENT_NAME

    return REMINDER_AGENT_NAME


# Find who owns a trigger this agent is allowed to touch
def _resolve_trigger_owner(trigger_id: int, *, agent_name: str) -> Optional[str]:
    """Return the owning identity for a trigger, or None if this agent has no access.

    An agent may modify its own triggers and the shared reminders. It may not
    reach another agent's triggers, even though they live in the same table.
    """
    # Imported lazily: the reminders package depends on this module at import time.
    from server.services.reminders import REMINDER_AGENT_NAME, is_reminder_agent

    candidates = [agent_name]
    if not is_reminder_agent(agent_name):
        candidates.append(REMINDER_AGENT_NAME)

    for owner in candidates:
        if _TRIGGER_SERVICE.fetch_trigger(trigger_id, agent_name=owner) is not None:
            return owner
    return None


# Return trigger tool callables bound to a specific agent
def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    """Return trigger tool callables bound to a specific agent."""

    return {
        "createTrigger": partial(_create_trigger_tool, agent_name=_default_reminder_owner(agent_name)),
        "updateTrigger": partial(_update_trigger_tool, agent_name=agent_name),
        "listTriggers": partial(_list_triggers_tool, agent_name=agent_name),
    }


__all__ = [
    "build_registry",
    "get_schemas",
]
