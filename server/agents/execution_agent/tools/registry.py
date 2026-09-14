"""Aggregate execution agent tool schemas and registries.

Legacy tools always load via `legacy.py`. Budgeted-only tools are appended when
`settings.budgeted_context` is true.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import legacy
from ....config import get_settings


def get_tool_schemas() -> List[Dict[str, Any]]:
    """Return OpenAI/OpenRouter-compatible tool schemas."""
    schemas = list(legacy.get_schemas())
    if get_settings().budgeted_context:
        from . import budgeted

        schemas.extend(budgeted.get_schemas())
    return schemas


def get_tool_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    """Return Python callables for executing tools by name."""
    registry = legacy.build_registry(agent_name)
    if get_settings().budgeted_context:
        from . import budgeted

        budgeted.extend_registry(registry, agent_name)
    return registry


__all__ = [
    "get_tool_registry",
    "get_tool_schemas",
]
