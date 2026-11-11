"""Aggregate execution agent tool schemas and registries."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import gmail, triggers
from ..tasks import get_task_registry, get_task_schemas


# Return OpenAI/OpenRouter-compatible tool schemas
def get_tool_schemas() -> List[Dict[str, Any]]:
    """Return OpenAI/OpenRouter-compatible tool schemas."""

    return [
        *gmail.get_schemas(),
        *get_task_schemas(),
        *triggers.get_schemas(),
    ]


# Return Python callables for executing tools by name
def get_tool_registry(agent_id: str) -> Dict[str, Callable[..., Any]]:
    """Return Python callables for executing tools by name, bound to the owning agent's id."""

    registry: Dict[str, Callable[..., Any]] = {}
    registry.update(gmail.build_registry(agent_id))
    registry.update(get_task_registry(agent_id))
    registry.update(triggers.build_registry(agent_id))
    return registry


__all__ = [
    "get_tool_registry",
    "get_tool_schemas",
]
