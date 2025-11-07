"""LLM utility functions for parsing and handling LLM responses."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

from server.logging_config import logger


@dataclass
class ToolCall:
    """
    Parsed tool invocation from an LLM response.

    Attributes:
        identifier: Optional unique ID for the tool call (from LLM)
        name: Name of the tool to invoke
        arguments: Dictionary of arguments to pass to the tool
    """

    identifier: Optional[str]
    name: str
    arguments: Dict[str, Any]


def extract_tool_calls(
    raw_tool_calls: List[Dict[str, Any]],
    *,
    validate_name: Optional[Callable[[str], Optional[str]]] = None,
    validate_arguments: Optional[Callable[[Any], tuple[Dict[str, Any], Optional[str]]]] = None,
    allow_multiple: bool = True,
) -> List[ToolCall]:
    """
    Extract and validate tool calls from LLM response.

    This function provides a unified way to parse tool calls from different
    agent types with customizable validation logic.

    Args:
        raw_tool_calls: List of raw tool call dictionaries from LLM
        validate_name: Optional callback to validate/transform tool names.
            Should return error message if invalid, None if valid.
        validate_arguments: Optional callback to parse/validate arguments.
            Should return (parsed_args, error_message) tuple.
        allow_multiple: Whether to allow multiple tool calls (default: True)

    Returns:
        List of parsed ToolCall objects

    Examples:
        >>> # Basic usage
        >>> raw = [{"function": {"name": "get_weather", "arguments": '{"city": "NYC"}'}}]
        >>> calls = extract_tool_calls(raw)
        >>> calls[0].name
        'get_weather'

        >>> # With validation
        >>> def validate_name(name: str) -> Optional[str]:
        ...     if "_" in name and " " in name:
        ...         return "Invalid tool name"
        ...     return None
        >>> extract_tool_calls(raw, validate_name=validate_name)
    """
    parsed: List[ToolCall] = []

    for raw in raw_tool_calls:
        function_block = raw.get("function") or {}
        name = function_block.get("name")

        # Validate tool name exists
        if not isinstance(name, str) or not name:
            logger.warning("Skipping tool call without name", extra={"tool": raw})
            continue

        # Custom name validation
        if validate_name:
            error = validate_name(name)
            if error:
                logger.warning(
                    "Tool call failed name validation",
                    extra={"tool": name, "error": error},
                )
                parsed.append(
                    ToolCall(
                        identifier=raw.get("id"),
                        name=name,
                        arguments={"__invalid_arguments__": error},
                    )
                )
                continue

        # Parse arguments
        raw_arguments = function_block.get("arguments")
        if validate_arguments:
            arguments, error = validate_arguments(raw_arguments)
        else:
            arguments, error = _default_argument_parser(raw_arguments)

        if error:
            logger.warning(
                "Tool call arguments invalid",
                extra={"tool": name, "error": error},
            )
            parsed.append(
                ToolCall(
                    identifier=raw.get("id"),
                    name=name,
                    arguments={"__invalid_arguments__": error},
                )
            )
            continue

        parsed.append(
            ToolCall(identifier=raw.get("id"), name=name, arguments=arguments)
        )

    # Limit to single tool call if requested
    if not allow_multiple and len(parsed) > 1:
        logger.warning(
            "Multiple tool calls detected, using only the first one",
            extra={"tools": [tc.name for tc in parsed]},
        )
        parsed = parsed[:1]

    return parsed


def _default_argument_parser(raw_arguments: Any) -> tuple[Dict[str, Any], Optional[str]]:
    """
    Default argument parser for tool calls.

    Handles None, dict, and JSON string arguments.

    Args:
        raw_arguments: The raw arguments from the LLM

    Returns:
        Tuple of (parsed_dict, error_message)
    """
    if raw_arguments is None:
        return {}, None

    if isinstance(raw_arguments, dict):
        return raw_arguments, None

    if isinstance(raw_arguments, str):
        if not raw_arguments.strip():
            return {}, None
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            return {}, f"invalid json: {exc}"
        if isinstance(parsed, dict):
            return parsed, None
        return {}, "decoded arguments were not an object"

    return {}, f"unsupported argument type: {type(raw_arguments).__name__}"


def validate_tool_name_simple(name: str) -> Optional[str]:
    """
    Simple tool name validator that rejects concatenated names.

    Useful for execution agents that want to reject common LLM hallucinations
    where multiple tool names are combined.

    Args:
        name: The tool name to validate

    Returns:
        Error message if invalid, None if valid

    Examples:
        >>> validate_tool_name_simple("get_weather")
        None
        >>> validate_tool_name_simple("get_weather_and_news")  # May be rejected
    """
    # Reject names with multiple separators suggesting concatenation
    separators = ['_', ' ', '-', '+']
    if any(sep in name for sep in separators) and len(name.split()) > 1:
        return f"Tool name appears to be concatenated: {name}"
    return None
