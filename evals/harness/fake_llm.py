"""A scripted, offline stand-in for ``request_chat_completion`` (OpenRouter response format)."""
from __future__ import annotations

import json
from typing import Any, Optional, Union

from evals.grading import ToolCall


class FakeLLM:
    """Returns one scripted assistant message per call, then a final text-only message.

    ``script[i]`` is the list of tool calls of the i-th response. A step entry may also be a raw
    dict, sent as-is, to script a malformed tool call. Every response carries a fixed
    ``usage`` block. The keyword arguments of each call are kept in ``requests``.
    """

    PROMPT_TOKENS = 100
    COMPLETION_TOKENS = 20
    FINAL_TEXT = "Done."

    def __init__(
        self,
        script: list[list[Union[ToolCall, dict]]],
        *,
        final_text: str = FINAL_TEXT,
        exc: Optional[Exception] = None,
    ) -> None:
        self.script = [list(step) for step in script]
        self.final_text = final_text
        self.exc = exc
        self.requests: list[dict[str, Any]] = []
        self._step = 0
        self._call_id = 0

    @classmethod
    def text(cls, s: str) -> "FakeLLM":
        """Always replies with text ``s`` and no tool calls."""
        return cls([], final_text=s)

    @classmethod
    def raising(cls, exc: Exception) -> "FakeLLM":
        """Every call raises ``exc``."""
        return cls([], exc=exc)

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        if self.exc is not None:
            raise self.exc
        if self._step < len(self.script):
            calls = self.script[self._step]
            self._step += 1
            message: dict[str, Any] = {
                "role": "assistant",
                "content": "",
                "tool_calls": [self._tool_call(c) for c in calls],
            }
        else:
            message = {"role": "assistant", "content": self.final_text}
        return {
            "id": f"fake-{len(self.requests)}",
            "object": "chat.completion",
            "model": kwargs.get("model", "fake"),
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
            "usage": {
                "prompt_tokens": self.PROMPT_TOKENS,
                "completion_tokens": self.COMPLETION_TOKENS,
                "total_tokens": self.PROMPT_TOKENS + self.COMPLETION_TOKENS,
            },
        }

    def _tool_call(self, call: Union[ToolCall, dict]) -> dict[str, Any]:
        if isinstance(call, dict):
            return call
        self._call_id += 1
        return {
            "id": f"call_{self._call_id}",
            "type": "function",
            "function": {"name": call.name, "arguments": json.dumps(call.args)},
        }
