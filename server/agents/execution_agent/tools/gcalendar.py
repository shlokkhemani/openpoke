"""Google Calendar tool schemas and actions for the execution agent."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from server.services.execution import get_execution_agent_logs
from server.services.gcalendar import execute_calendar_tool, get_active_calendar_user_id

_CALENDAR_AGENT_NAME = "calendar-execution-agent"

_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": "Create a Google Calendar event with title, date/time, location, and attendees.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Event title/summary.",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in ISO 8601 format (e.g., '2025-11-04T14:00:00Z' or '2025-11-04T14:00:00-05:00').",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in ISO 8601 format.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description/notes.",
                    },
                    "location": {
                        "type": "string",
                        "description": "Optional event location.",
                    },
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of attendee email addresses.",
                    },
                    "timezone": {
                        "type": "string",
                        "description": "Optional timezone (e.g., 'America/New_York'). Defaults to calendar's timezone.",
                    },
                },
                "required": ["summary", "start_time", "end_time"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": "List upcoming Google Calendar events within a time range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {
                        "type": "string",
                        "description": "Start of time range in ISO 8601 format.",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "End of time range in ISO 8601 format.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of events to return (default: 10).",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar ID to query (default: 'primary').",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_update_event",
            "description": "Update an existing Google Calendar event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "Calendar event ID to update.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Updated event title/summary.",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Updated start time in ISO 8601 format.",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "Updated end time in ISO 8601 format.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Updated event description.",
                    },
                    "location": {
                        "type": "string",
                        "description": "Updated event location.",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar ID (default: 'primary').",
                    },
                },
                "required": ["event_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_delete_event",
            "description": "Delete a Google Calendar event by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "Calendar event ID to delete.",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar ID (default: 'primary').",
                    },
                },
                "required": ["event_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_find_free_time",
            "description": "Find free time slots in the calendar within a time range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {
                        "type": "string",
                        "description": "Start of time range in ISO 8601 format.",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "End of time range in ISO 8601 format.",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Desired duration of free slot in minutes.",
                    },
                },
                "required": ["time_min", "time_max"],
                "additionalProperties": False,
            },
        },
    },
]

_LOG_STORE = get_execution_agent_logs()


def get_schemas() -> List[Dict[str, Any]]:
    """Return OpenAI/OpenRouter-compatible tool schemas for Google Calendar."""
    return _SCHEMAS


def _log_action(agent_name: str, action: str) -> None:
    """Log calendar action to the execution agent log."""
    _LOG_STORE.record_action(agent_name, action)


def _execute_calendar_action(
    agent_name: str,
    tool_name: str,
    composio_action: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Execute a calendar tool via Composio and log the action.
    
    Args:
        agent_name: Name of the execution agent
        tool_name: Name of the calendar tool being called
        composio_action: Composio action identifier (e.g., GOOGLECALENDAR_CREATE_EVENT)
        arguments: Tool arguments
        
    Returns:
        Tool execution result
    """
    user_id = get_active_calendar_user_id()
    
    _log_action(agent_name, f"Calling {tool_name} with arguments: {json.dumps(arguments, default=str)[:200]}")
    
    result = execute_calendar_tool(
        tool_name=composio_action,
        user_id=user_id,
        arguments=arguments,
    )
    
    if isinstance(result, dict) and result.get("error"):
        _log_action(agent_name, f"{tool_name} failed: {result['error']}")
    else:
        _log_action(agent_name, f"{tool_name} completed successfully")
    
    return result


# Tool handler functions
def _calendar_create_event(agent_name: str, **kwargs: Any) -> Dict[str, Any]:
    """Create a new calendar event."""
    return _execute_calendar_action(
        agent_name=agent_name,
        tool_name="calendar_create_event",
        composio_action="GOOGLECALENDAR_CREATE_EVENT",
        arguments=kwargs,
    )


def _calendar_list_events(agent_name: str, **kwargs: Any) -> Dict[str, Any]:
    """List calendar events."""
    return _execute_calendar_action(
        agent_name=agent_name,
        tool_name="calendar_list_events",
        composio_action="GOOGLECALENDAR_EVENTS_LIST",
        arguments=kwargs,
    )


def _calendar_update_event(agent_name: str, **kwargs: Any) -> Dict[str, Any]:
    """Update an existing calendar event."""
    return _execute_calendar_action(
        agent_name=agent_name,
        tool_name="calendar_update_event",
        composio_action="GOOGLECALENDAR_UPDATE_EVENT",
        arguments=kwargs,
    )


def _calendar_delete_event(agent_name: str, **kwargs: Any) -> Dict[str, Any]:
    """Delete a calendar event."""
    return _execute_calendar_action(
        agent_name=agent_name,
        tool_name="calendar_delete_event",
        composio_action="GOOGLECALENDAR_DELETE_EVENT",
        arguments=kwargs,
    )


def _calendar_find_free_time(agent_name: str, **kwargs: Any) -> Dict[str, Any]:
    """Find free time slots in the calendar."""
    return _execute_calendar_action(
        agent_name=agent_name,
        tool_name="calendar_find_free_time",
        composio_action="GOOGLECALENDAR_FIND_FREE_SLOTS",
        arguments=kwargs,
    )


def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    """
    Build a registry of calendar tool callables for the execution agent.
    
    Args:
        agent_name: Name of the execution agent
        
    Returns:
        Dictionary mapping tool names to callable functions
    """
    from functools import partial
    
    return {
        "calendar_create_event": partial(_calendar_create_event, agent_name),
        "calendar_list_events": partial(_calendar_list_events, agent_name),
        "calendar_update_event": partial(_calendar_update_event, agent_name),
        "calendar_delete_event": partial(_calendar_delete_event, agent_name),
        "calendar_find_free_time": partial(_calendar_find_free_time, agent_name),
    }


__all__ = [
    "get_schemas",
    "build_registry",
]
