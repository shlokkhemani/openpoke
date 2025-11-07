"""Shared tool validation utilities for agents."""

from functools import lru_cache
from typing import List, Optional, Set, Tuple


def split_known_tools(name: str, known_tools: Set[str]) -> List[str]:
    """
    Attempt to split a concatenated tool name into known tool identifiers.

    This function tries to detect when an LLM has hallucinated a concatenated
    tool name by greedily matching against known tool names from longest to shortest.

    Args:
        name: The potentially concatenated tool name
        known_tools: Set of valid tool names to match against

    Returns:
    List of individual tool names if the input is a concatenation,
    empty list if no valid split is found or the input is a single tool

    Examples:
        >>> split_known_tools("send_message_to_agentsend_draft",
        ...                   {"send_message_to_agent", "send_draft"})
        ['send_message_to_agent', 'send_draft']

        >>> split_known_tools("gmail_send_email",
        ...                   {"gmail_send_email"})
        []  # Single valid tool, not a concatenation
    """

    separators = {"_", " ", "-", "+"}
    sorted_tools = tuple(sorted(known_tools, key=len, reverse=True))

    @lru_cache(maxsize=None)
    def _split_from(index: int) -> Optional[Tuple[str, ...]]:
        if index >= len(name):
            return tuple()

        # Allow separators only between tools, not at the very start
        current = index
        if current > 0:
            while current < len(name) and name[current] in separators:
                current += 1
            if current >= len(name):
                return tuple()

        for candidate in sorted_tools:
            if name.startswith(candidate, current):
                remainder = _split_from(current + len(candidate))
                if remainder is not None:
                    return (candidate,) + remainder

        return None

    components = _split_from(0)
    if not components or len(components) <= 1:
        return []

    return list(components)


def get_interaction_tool_names() -> Set[str]:
    """
    Get the set of known interaction agent tool names.

    Returns:
        Set of valid interaction agent tool names
    """
    return {
        "send_message_to_agent",
        "send_message_to_user",
        "send_draft",
        "wait",
        "remove_agent",
        "add_lesson",
        "get_lessons",
        "delete_lesson",
        "add_memory",
        "get_memories",
        "delete_memory",
    }


def get_execution_tool_names() -> Set[str]:
    """
    Get the set of known execution agent tool names.

    This dynamically imports and extracts tool names from the execution agent
    tool registry to avoid circular imports.

    Returns:
        Set of valid execution agent tool names
    """
    from ..agents.execution_agent.tools import get_tool_schemas

    tool_names: Set[str] = set()
    schemas = get_tool_schemas()

    for schema in schemas:
        if "function" in schema and "name" in schema["function"]:
            tool_names.add(schema["function"]["name"])

    return tool_names


def get_all_known_tool_names() -> Set[str]:
    """
    Get the combined set of all known tool names from both agents.

    Returns:
        Set of all valid tool names
    """
    return get_interaction_tool_names() | get_execution_tool_names()


__all__ = [
    "split_known_tools",
    "get_interaction_tool_names",
    "get_execution_tool_names",
    "get_all_known_tool_names",
]
