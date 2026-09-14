"""Interaction-agent tool package (legacy + budgeted)."""

from __future__ import annotations

from .budgeted import digest_entry
from .dispatch import get_tool_schemas, handle_tool_call
from .legacy import get_execution_batch_manager, set_execution_batch_manager
from .types import ToolResult

__all__ = [
    "ToolResult",
    "digest_entry",
    "get_execution_batch_manager",
    "get_tool_schemas",
    "handle_tool_call",
    "set_execution_batch_manager",
]
