"""Execution agent: Gmail tool routing, failure handling, and batch aggregation."""

from __future__ import annotations

import pytest

from server.config import Settings
from server.agents.execution_agent import batch_manager as batch_module
from server.agents.execution_agent import runtime as execution_runtime
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.execution_agent.runtime import ExecutionResult
from server.agents.execution_agent.tools import gmail as gmail_tools
from server.tests.conftest import completion, tool_call


@pytest.fixture
def composio_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    """Record Composio tool invocations instead of calling the network."""
    calls: list[tuple[str, dict]] = []

    def _fake_execute(tool_name: str, user_id: str, *, arguments=None):
        calls.append((tool_name, dict(arguments or {})))
        return {"data": {"id": f"stub-{len(calls)}"}}

    monkeypatch.setattr(gmail_tools, "execute_gmail_tool", _fake_execute)
    return calls


@pytest.fixture
def gmail_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gmail_tools, "get_active_gmail_user_id", lambda: "user-123")


@pytest.fixture
def gmail_disconnected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gmail_tools, "get_active_gmail_user_id", lambda: None)


async def _run_agent(scripted_llm, responses, name: str = "Email to Alice"):
    fake = scripted_llm(execution_runtime, responses)
    runtime = execution_runtime.ExecutionAgentRuntime(agent_name=name)
    return await runtime.execute("do the email task"), fake


async def test_draft_is_created_without_sending(
    scripted_llm, composio_calls, gmail_connected
) -> None:
    """Draft-before-send: a draft turn must never trigger a send."""
    responses = [
        completion(
            tool_calls=[
                tool_call(
                    "gmail_create_draft",
                    {
                        "recipient_email": "alice@example.com",
                        "subject": "Contract",
                        "body": "Here is the draft.",
                    },
                )
            ]
        ),
        completion("Draft ready for review."),
    ]

    result, fake = await _run_agent(scripted_llm, responses)

    fake.assert_drained()
    assert result.success is True
    assert [name for name, _ in composio_calls] == ["GMAIL_CREATE_EMAIL_DRAFT"]
    assert composio_calls[0][1]["recipient_email"] == "alice@example.com"
    assert result.tools_executed == ["gmail_create_draft"]


async def test_send_uses_draft_id_from_previous_step(
    scripted_llm, composio_calls, gmail_connected
) -> None:
    responses = [
        completion(
            tool_calls=[
                tool_call("gmail_create_draft", {"recipient_email": "a@b.com", "subject": "s", "body": "b"})
            ]
        ),
        completion(tool_calls=[tool_call("gmail_execute_draft", {"draft_id": "stub-1"}, call_id="call_2")]),
        completion("Sent."),
    ]

    result, fake = await _run_agent(scripted_llm, responses)

    fake.assert_drained()
    assert [name for name, _ in composio_calls] == ["GMAIL_CREATE_EMAIL_DRAFT", "GMAIL_SEND_DRAFT"]
    assert composio_calls[1][1]["draft_id"] == "stub-1"
    assert result.success is True


async def test_unknown_tool_result_is_fed_back_and_loop_continues(
    scripted_llm, composio_calls, gmail_connected
) -> None:
    responses = [
        completion(tool_calls=[tool_call("gmail_buy_a_car", {})]),
        completion("That tool does not exist, so I stopped."),
    ]

    result, fake = await _run_agent(scripted_llm, responses)

    fake.assert_drained()
    assert result.success is True
    assert composio_calls == []
    assert "does not exist" in result.response


async def test_disconnected_gmail_reports_instead_of_raising(
    scripted_llm, composio_calls, gmail_disconnected
) -> None:
    responses = [
        completion(
            tool_calls=[
                tool_call("gmail_create_draft", {"recipient_email": "a@b.com", "subject": "s", "body": "b"})
            ]
        ),
        completion("Gmail is not connected."),
    ]

    result, fake = await _run_agent(scripted_llm, responses)

    fake.assert_drained()
    assert composio_calls == []
    assert result.success is True


async def test_composio_failure_is_reported_to_the_model(
    scripted_llm, monkeypatch: pytest.MonkeyPatch, gmail_connected, execution_logs
) -> None:
    """A tool error is fed back to the model rather than aborting the run."""

    def _boom(tool_name: str, user_id: str, *, arguments=None):
        raise RuntimeError("composio exploded")

    monkeypatch.setattr(gmail_tools, "execute_gmail_tool", _boom)

    responses = [
        completion(
            tool_calls=[
                tool_call("gmail_create_draft", {"recipient_email": "a@b.com", "subject": "s", "body": "b"})
            ]
        ),
        completion("The draft failed because the mail service errored."),
    ]

    result, fake = await _run_agent(scripted_llm, responses)

    fake.assert_drained()
    assert result.success is True
    assert result.tools_executed == ["gmail_create_draft"]
    assert "mail service errored" in result.response

    # The error text reached the model as the tool result
    second_call_messages = fake.calls[1]["messages"]
    tool_message = [m for m in second_call_messages if m.get("role") == "tool"][-1]
    assert "composio exploded" in tool_message["content"]


async def test_agent_history_is_carried_between_runs(
    scripted_llm, composio_calls, gmail_connected, execution_logs
) -> None:
    first = [completion("Noted the first request.")]
    await _run_agent(scripted_llm, first)

    second = [completion("Second time around.")]
    fake = scripted_llm(execution_runtime, second)
    runtime = execution_runtime.ExecutionAgentRuntime(agent_name="Email to Alice")
    await runtime.execute("follow up")

    system_prompt = fake.calls[0]["system"]
    assert "Noted the first request." in system_prompt


def test_batch_payload_lists_each_agent_once() -> None:
    manager = ExecutionBatchManager()
    results = [
        ExecutionResult(agent_name="Email to Alice", success=True, response="draft ready"),
        ExecutionResult(agent_name="Budget Analysis", success=False, response="failed", error="timeout"),
    ]

    payload = manager._format_batch_payload(results)

    lines = payload.splitlines()
    assert lines[0] == "[SUCCESS] Email to Alice: draft ready"
    assert lines[1] == "[FAILED] Budget Analysis: failed"


def test_batch_payload_handles_empty_response() -> None:
    manager = ExecutionBatchManager()
    payload = manager._format_batch_payload(
        [ExecutionResult(agent_name="Agent A", success=True, response="")]
    )

    assert "(no response provided)" in payload


def test_batch_timeout_follows_the_llm_timeout() -> None:
    """Local generation is slow, so the 90s default would fake timeouts."""
    assert ExecutionBatchManager().timeout_seconds == 300

    manager = ExecutionBatchManager(timeout_seconds=45)
    assert manager.timeout_seconds == 45


async def test_batch_reports_a_timeout_without_hanging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ExecutionBatchManager(timeout_seconds=0)
    monkeypatch.setattr(manager, "_dispatch_to_interaction_agent", _noop)

    class _SlowRuntime:
        def __init__(self, agent_name: str) -> None:
            self.agent_name = agent_name

        async def execute(self, instructions: str) -> ExecutionResult:  # pragma: no cover
            raise AssertionError("the timeout should fire before execute returns")

    monkeypatch.setattr(batch_module, "ExecutionAgentRuntime", _SlowRuntime)

    result = await manager.execute_agent("Agent A", "do work")

    assert result.success is False
    assert "timed out" in result.response


async def _noop(payload: str) -> None:
    return None


async def test_no_single_model_setting_is_ignored_when_base_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only an unset LLM_BASE_URL blocks execution, never a missing API key."""
    settings = Settings(llm_base_url="", llm_api_key=None)
    monkeypatch.setattr(execution_runtime, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        execution_runtime.ExecutionAgentRuntime(agent_name="Email to Alice")


def test_agent_works_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(llm_api_key=None)
    monkeypatch.setattr(execution_runtime, "get_settings", lambda: settings)

    runtime = execution_runtime.ExecutionAgentRuntime(agent_name="Email to Alice")

    assert runtime.api_key is None
    assert runtime.base_url == settings.llm_base_url


async def test_reasoning_only_reply_finishes_the_run(scripted_llm, composio_calls, gmail_connected) -> None:
    """A reasoning-only completion must not look like an empty final response."""
    reasoning_only = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "Nothing to do; the draft already exists.",
                }
            }
        ]
    }

    result, fake = await _run_agent(scripted_llm, [reasoning_only])

    fake.assert_drained()
    assert result.success is True
    assert "already exists" in result.response


async def test_batch_dispatches_once_when_all_agents_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ExecutionBatchManager()
    dispatches: list[str] = []

    async def _capture(payload: str) -> None:
        dispatches.append(payload)

    monkeypatch.setattr(manager, "_dispatch_to_interaction_agent", _capture)

    await manager._register_pending_execution("Agent A", "one", "req-1")
    batch_id = await manager._register_pending_execution("Agent B", "two", "req-2")

    await manager._complete_execution(
        batch_id, ExecutionResult(agent_name="Agent A", success=True, response="a done"), "Agent A"
    )
    assert dispatches == [], "must wait for the whole batch"

    await manager._complete_execution(
        batch_id, ExecutionResult(agent_name="Agent B", success=True, response="b done"), "Agent B"
    )
    assert len(dispatches) == 1
    assert "Agent A: a done" in dispatches[0]
    assert "Agent B: b done" in dispatches[0]
