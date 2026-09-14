"""Schema list and tool-call router for the interaction agent."""

from __future__ import annotations

import json
from typing import Any

from ....config import get_settings
from ....logging_config import logger
from . import budgeted, legacy
from .types import ToolResult


def get_tool_schemas():
    """Return OpenAI-compatible tool schemas (budgeted tools only under the budgeted strategy)."""
    if get_settings().budgeted_context:
        return [*legacy.TOOL_SCHEMAS, *budgeted.budgeted_schemas()]
    return legacy.TOOL_SCHEMAS


def handle_tool_call(name: str, arguments: Any) -> ToolResult:
    """Handle tool calls from interaction agent."""
    try:
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        elif isinstance(arguments, dict):
            args = arguments
        else:
            return ToolResult(success=False, payload={"error": "Invalid arguments format"})

        if name == "send_message_to_agent":
            return legacy.send_message_to_agent(**args)
        if name == "send_message_to_user":
            return legacy.send_message_to_user(**args)
        if name == "send_draft":
            return legacy.send_draft(**args)
        if name == "wait":
            return legacy.wait(**args)
        if name == "recall_history":
            return budgeted.recall_history(**args)
        if name == "send_draft_v2":
            return budgeted.send_draft_v2(**args)
        if name == "find_worker":
            return budgeted.find_worker(**args)

        logger.warning("unexpected tool", extra={"tool": name})
        return ToolResult(success=False, payload={"error": f"Unknown tool: {name}"})
    except json.JSONDecodeError:
        return ToolResult(success=False, payload={"error": "Invalid JSON"})
    except TypeError as exc:
        return ToolResult(success=False, payload={"error": f"Missing required arguments: {exc}"})
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("tool call failed", extra={"tool": name, "error": str(exc)})
        return ToolResult(success=False, payload={"error": "Failed to execute"})


__all__ = ["ToolResult", "get_tool_schemas", "handle_tool_call"]
