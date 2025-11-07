"""Shared tool result formatting utilities for agent runtimes."""

from typing import Any, Dict

from ..utils.json_utils import safe_json_dump


def format_tool_result(
    tool_name: str,
    success: bool,
    result: Any,
    arguments: Dict[str, Any],
) -> str:
    """Build a structured string for tool responses.

    Args:
        tool_name: Name of the tool that was executed
        success: Whether the tool execution was successful
        result: The result payload from tool execution
        arguments: The arguments passed to the tool

    Returns:
        JSON string representation of the tool result
    """
    # Filter out invalid arguments marker
    clean_arguments = {
        key: value
        for key, value in arguments.items()
        if key != "__invalid_arguments__"
    }

    payload: Dict[str, Any] = {
        "tool": tool_name,
        "status": "success" if success else "error",
        "arguments": clean_arguments,
    }

    if result is not None:
        key = "result" if success else "error"
        payload[key] = result

    return safe_json_dump(payload)