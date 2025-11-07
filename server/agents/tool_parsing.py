"""Shared tool parsing utilities for agent runtimes."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from ..logging_config import logger
from ..utils.json_utils import safe_json_load
from ..utils.tool_validation import split_known_tools


@dataclass
class ParsedToolCall:
    """Normalized tool call representation."""

    identifier: Optional[str]
    name: str
    arguments: Dict[str, Any]


def extract_tool_calls(raw_tools: List[Dict[str, Any]], known_tools: Set[str]) -> List[Dict[str, Any]]:
    """Extract and validate tool calls from LLM response.

    Args:
        raw_tools: Raw tool calls from LLM response
        known_tools: List of valid tool names

    Returns:
        List of validated tool call dictionaries
    """
    tool_calls: List[Dict[str, Any]] = []

    for tool in raw_tools:
        function = tool.get("function", {})
        name = function.get("name", "")
        args = function.get("arguments", "")

        # Validate tool name - reject malformed names
        if not name or not isinstance(name, str):
            logger.warning("Tool call missing or invalid name: %s", tool)
            continue

        # Check for concatenated tool names (common LLM hallucination)
        concatenated = split_known_tools(name, known_tools)
        if concatenated:
            logger.warning(
                "Tool call rejected - concatenated name detected: %s (components: %s)",
                name,
                concatenated,
            )
            # Add error tool call to inform the LLM about the mistake
            tool_calls.append({
                "id": tool.get("id"),
                "name": concatenated[0],  # Use first valid tool name
                "arguments": {
                    "__invalid_arguments__": (
                        f"CRITICAL ERROR: You attempted to call multiple tools in a single invocation. "
                        f"The tool name '{name}' is invalid because it combines these tools: {', '.join(concatenated)}. "
                        f"You MUST call each tool separately in its own tool invocation. "
                        f"Make separate calls for: {' and '.join(concatenated)}."
                    )
                },
            })
            continue

        # Check if tool name is valid (exists in registry)
        if name not in known_tools:
            logger.warning("Tool call for unknown tool: %s", name)
            tool_calls.append({
                "id": tool.get("id"),
                "name": name,
                "arguments": {
                    "__invalid_arguments__": (
                        f"ERROR: Unknown tool '{name}'. "
                        f"Please use only the tools provided in your schema."
                    )
                },
            })
            continue

        # Parse arguments
        try:
            if isinstance(args, str):
                parsed_args = json.loads(args)
            elif isinstance(args, dict):
                parsed_args = args
            else:
                parsed_args = {}
        except (json.JSONDecodeError, TypeError):
            parsed_args = {"__invalid_arguments__": f"Invalid JSON arguments: {args}"}

        tool_calls.append({
            "id": tool.get("id"),
            "name": name,
            "arguments": parsed_args,
        })

    return tool_calls


def parse_tool_calls(raw_tool_calls: List[Dict[str, Any]], known_tools: Set[str]) -> List[ParsedToolCall]:
    """Parse and normalize tool calls from LLM response into structured objects.

    Args:
        raw_tool_calls: Raw tool calls from LLM response
        known_tools: List of valid tool names

    Returns:
        List of ParsedToolCall objects
    """
    parsed: List[ParsedToolCall] = []

    for raw in raw_tool_calls:
        function_block = raw.get("function") or {}
        name = function_block.get("name")

        if not isinstance(name, str) or not name:
            logger.warning("Skipping tool call without name", extra={"tool": raw})
            continue

        # Check for concatenated tool names BEFORE parsing arguments
        concatenated = split_known_tools(name, known_tools)
        if concatenated:
            logger.warning(
                "Tool call combined multiple tools",
                extra={"tool": name, "components": concatenated},
            )
            parsed.append(
                ParsedToolCall(
                    identifier=raw.get("id"),
                    name=concatenated[0],  # Use first valid tool name
                    arguments={
                        "__invalid_arguments__": (
                            f"CRITICAL ERROR: You attempted to call multiple tools in a single invocation. "
                            f"The tool name '{name}' is invalid because it combines these tools: {', '.join(concatenated)}. "
                            f"You MUST call each tool separately in its own tool invocation. "
                            f"Make separate calls for: {' and '.join(concatenated)}."
                        )
                    },
                )
            )
            continue

        arguments, error = _parse_tool_arguments(function_block.get("arguments"))
        if error:
            logger.warning("Tool call arguments invalid", extra={"tool": name, "error": error})
            parsed.append(
                ParsedToolCall(
                    identifier=raw.get("id"),
                    name=name,
                    arguments={"__invalid_arguments__": error},
                )
            )
            continue

        parsed.append(
            ParsedToolCall(
                identifier=raw.get("id"),
                name=name,
                arguments=arguments,
            )
        )

    return parsed


def _parse_tool_arguments(raw_arguments: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Convert tool arguments into a dictionary, reporting errors."""
    return safe_json_load(raw_arguments)