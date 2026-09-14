"""Compatibility shim — prefer `server.agents.interaction_agent.context.history`."""

from ...agents.interaction_agent.context.history import (  # noqa: F401
    BuiltContext,
    build_history,
    recall_entries,
    render_entry,
)

__all__ = ["BuiltContext", "build_history", "recall_entries", "render_entry"]
