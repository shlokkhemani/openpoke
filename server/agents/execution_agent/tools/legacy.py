"""Legacy (always-on) execution agent tools.

Gmail, triggers, and task tools are registered for every strategy.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import gmail, triggers
from ..tasks import get_task_registry, get_task_schemas


def get_schemas() -> List[Dict[str, Any]]:
    return [
        *gmail.get_schemas(),
        *get_task_schemas(),
        *triggers.get_schemas(),
    ]


def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    registry: Dict[str, Callable[..., Any]] = {}
    registry.update(gmail.build_registry(agent_name))
    registry.update(get_task_registry(agent_name))
    registry.update(triggers.build_registry(agent_name))
    return registry


__all__ = ["get_schemas", "build_registry"]
