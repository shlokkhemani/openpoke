"""The execution agent's behaviour when the guardrail holds a tool call."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from server.agents.execution_agent import runtime as execution_runtime
from tests.conftest import noul_answers


ASSIGNMENT = "Reply to Dana confirming Friday."


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch, reload_settings) -> Any:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    reload_settings()

    executed: List[str] = []

    class _Agent:
        name = "dana-agent"

        def build_system_prompt_with_history(self) -> str:
            return "system"

        def record_tool_execution(self, *args: Any, **kwargs: Any) -> None:
            return None

        def record_response(self, *args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(execution_runtime, "ExecutionAgent", lambda name: _Agent())
    monkeypatch.setattr(execution_runtime, "get_tool_schemas", lambda: [])

    def _send(**kwargs: Any) -> Dict[str, Any]:
        executed.append("GMAIL_SEND_EMAIL")
        return {"status": "sent"}

    monkeypatch.setattr(
        execution_runtime,
        "get_tool_registry",
        lambda agent_name: {"GMAIL_SEND_EMAIL": _send},
    )

    turns: List[Dict[str, Any]] = [
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "GMAIL_SEND_EMAIL",
                                    "arguments": '{"to": "someone-else@example.com"}',
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {"choices": [{"message": {"content": "Done."}}]},
    ]

    async def fake_request_chat_completion(**kwargs: Any) -> Dict[str, Any]:
        return turns.pop(0) if turns else {"choices": [{"message": {"content": "Done."}}]}

    monkeypatch.setattr(execution_runtime, "request_chat_completion", fake_request_chat_completion)

    return execution_runtime.ExecutionAgentRuntime("dana-agent"), executed


async def test_held_call_is_not_executed(
    jev_env: None, jev_transport, agent: Any
) -> None:
    runtime, executed = agent
    jev_transport(noul_answers(intent_mismatch=0.95, off_task=0.9, irreversible=0.99))

    result = await runtime.execute(ASSIGNMENT)

    assert result.success is True, "a held call is a correction, not a failure"
    assert executed == [], "the send must never reach Gmail"
    assert result.tools_executed == [], "a held call did not execute"


async def test_faithful_call_still_runs(jev_env: None, jev_transport, agent: Any) -> None:
    runtime, executed = agent
    jev_transport(noul_answers(intent_mismatch=0.02, off_task=0.03, irreversible=0.99))

    await runtime.execute(ASSIGNMENT)

    assert executed == ["GMAIL_SEND_EMAIL"]


async def test_advisory_call_runs_and_the_agent_is_told(
    jev_env: None, jev_transport, agent: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A steered call must still execute, and the judgement must reach the agent
    # in the tool result rather than vanishing into a log line.
    runtime, executed = agent
    jev_transport(noul_answers(intent_mismatch=0.2, off_task=0.95, irreversible=0.99))
    recorded: list = []
    monkeypatch.setattr(
        runtime.agent, "record_tool_execution", lambda *args, **kwargs: recorded.append(args)
    )

    await runtime.execute(ASSIGNMENT)

    assert executed == ["GMAIL_SEND_EMAIL"]
    assert any("guardrail_note" in str(args) for args in recorded)
    assert any("off_task=0.95" in str(args) for args in recorded)


async def test_jev_outage_does_not_block_the_agent(
    jev_env: None, jev_transport, agent: Any
) -> None:
    runtime, executed = agent
    jev_transport({}, status=500)

    await runtime.execute(ASSIGNMENT)

    assert executed == ["GMAIL_SEND_EMAIL"], "the guardrail fails open"


async def test_guardrail_is_inert_without_jev(agent: Any) -> None:
    runtime, executed = agent

    await runtime.execute(ASSIGNMENT)

    assert executed == ["GMAIL_SEND_EMAIL"]
