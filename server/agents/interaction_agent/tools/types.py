"""Shared tool result type for the interaction agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolResult:
    """Standardized payload returned by interaction-agent tools."""

    success: bool
    payload: Any = None
    user_message: Optional[str] = None
    recorded_reply: bool = False


__all__ = ["ToolResult"]
