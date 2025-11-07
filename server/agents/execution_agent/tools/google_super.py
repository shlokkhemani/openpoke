"""Google Super tool schemas and handlers for the execution agent."""

from __future__ import annotations

import json
from functools import partial
from typing import Any, Callable, Dict, List, Optional

from server.services.execution import get_execution_agent_logs
from server.services.googlesuper import (
    describe_google_super_tool,
    execute_google_super_tool,
    get_active_google_super_user_id,
    get_connected_google_super_account_id,
    list_google_super_tools,
)

_AGENT_NAME = "googlesuper"

_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "googlesuperListTools",
            "description": "List Google Super (Composio) tools with optional search filtering.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Optional case-insensitive search query to filter tool names or descriptions.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tools to return (default 20, max 50).",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "googlesuperDescribeTool",
            "description": "Fetch the schema and metadata for a specific Google Super tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Exact Google Super tool identifier (for example GOOGLESUPER_CREATE_EVENT).",
                    }
                },
                "required": ["tool_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "googlesuperExecute",
            "description": "Execute a Google Super tool by name with the provided arguments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Exact Google Super tool identifier to execute.",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "JSON object of arguments to forward to the tool (consult describe/list responses).",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "Optional Composio user id override; defaults to the configured Google Super account.",
                    },
                },
                "required": ["tool_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "googlesuperGetActiveAccount",
            "description": "Return the configured Google Super connected account identifiers.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]

_LOG_STORE = get_execution_agent_logs()


def get_schemas() -> List[Dict[str, Any]]:
    """Return Google Super tool schemas."""

    return _SCHEMAS


def _record(agent_name: str, message: str) -> None:
    _LOG_STORE.record_action(agent_name, description=message)


def _serialize_arguments(arguments: Optional[Dict[str, Any]]) -> str:
    if not arguments:
        return "{}"
    try:
        return json.dumps(arguments, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(arguments)


def _list_tools(
    agent_name: str,
    *,
    search: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    result = list_google_super_tools(search=search, limit=limit)
    if "error" in result:
        _record(agent_name, f"googlesuperListTools failed | search={search!r} | error={result['error']}")
    else:
        returned = result.get("returned") or len(result.get("tools", []))
        _record(agent_name, f"googlesuperListTools succeeded | search={search!r} | returned={returned}")
    return result


def _describe_tool(
    agent_name: str,
    *,
    tool_name: str,
) -> Dict[str, Any]:
    result = describe_google_super_tool(tool_name)
    if "error" in result:
        _record(agent_name, f"googlesuperDescribeTool failed | tool={tool_name} | error={result['error']}")
    else:
        _record(agent_name, f"googlesuperDescribeTool succeeded | tool={tool_name}")
    return result


def _execute_tool(
    agent_name: str,
    *,
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload_preview = _serialize_arguments(arguments)
    result = execute_google_super_tool(tool_name, arguments=arguments, user_id=user_id)
    if "error" in result:
        _record(
            agent_name,
            f"googlesuperExecute failed | tool={tool_name} | user_id={user_id or 'default'} | args={payload_preview} | error={result['error']}",
        )
    else:
        _record(
            agent_name,
            f"googlesuperExecute succeeded | tool={tool_name} | user_id={user_id or 'default'} | args={payload_preview}",
        )
    return result


def _get_active_account(agent_name: str) -> Dict[str, Any]:
    user_id = get_active_google_super_user_id()
    account_id = get_connected_google_super_account_id()
    _record(agent_name, f"googlesuperGetActiveAccount | user_id={user_id or 'unset'} | account_id={account_id or 'unset'}")
    return {
        "user_id": user_id,
        "connected_account_id": account_id,
    }


def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    """Return Google Super tool callables bound to a specific agent."""

    return {
        "googlesuperListTools": partial(_list_tools, agent_name),
        "googlesuperDescribeTool": partial(_describe_tool, agent_name),
        "googlesuperExecute": partial(_execute_tool, agent_name),
        "googlesuperGetActiveAccount": partial(_get_active_account, agent_name),
    }


__all__ = [
    "build_registry",
    "get_schemas",
]
