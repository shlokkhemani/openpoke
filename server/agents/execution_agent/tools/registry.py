"""Aggregate execution agent tool schemas and registries."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import gcalendar, gmail, google_super, search, triggers
from ..tasks import get_task_registry, get_task_schemas


# Return OpenAI/OpenRouter-compatible tool schemas
def get_tool_schemas() -> List[Dict[str, Any]]:
    """Return OpenAI/OpenRouter-compatible tool schemas."""

    return [
        *gcalendar.get_schemas(),
        *gmail.get_schemas(),
        *google_super.get_schemas(),
        *search.get_schemas(),
        *get_task_schemas(),
        *triggers.get_schemas(),
    ]


# Return Python callables for executing tools by name
def get_tool_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    """Return Python callables for executing tools by name."""

    registry: Dict[str, Callable[..., Any]] = {}
    registry.update(gcalendar.build_registry(agent_name))
    registry.update(gmail.build_registry(agent_name))
    registry.update(google_super.build_registry(agent_name))
    registry.update(search.build_registry(agent_name))
    registry.update(get_task_registry(agent_name))
    registry.update(triggers.build_registry(agent_name))
    return registry


__all__ = [
    "get_tool_registry",
    "get_tool_schemas",
]
