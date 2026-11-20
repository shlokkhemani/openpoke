"""Interaction agent: routing, tool-call handling, and failure recovery."""

from __future__ import annotations

import asyncio

import pytest

from server.agents.execution_agent.runtime import ExecutionResult
from server.agents.interaction_agent import runtime as interaction_runtime
from server.openrouter_client import OpenRouterError
from server.tests.conftest import completion, tool_call


@pytest.fixture
def stub_dispatched_agents(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture dispatched agent work without running a real execution agent."""
    dispatched: list[tuple[str, str]] = []

    async def _fake_execute(agent_name: str, instructions: str, request_id: str | None = None):
        dispatched.append((agent_name, instructions))
        return ExecutionResult(agent_name=agent_name, success=True, response="done", tools_executed=[])

    from server.agents.interaction_agent import tools as interaction_tools

    monkeypatch.setattr(
        interaction_tools._EXECUTION_BATCH_MANAGER, "execute_agent", _fake_execute
    )
    return dispatched


async def _run(scripted_llm, responses, stub_dispatched_agents, message: str = "email alice"):
    fake = scripted_llm(interaction_runtime, responses)
    runtime = interaction_runtime.InteractionAgentRuntime()
    result = await runtime.execute(user_message=message)
    # Agent dispatch happens on a background task; let it run before asserting
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    return result, fake


async def test_routes_work_to_execution_agent(
    scripted_llm, stub_dispatched_agents, conversation_log, execution_logs, roster
) -> None:
    responses = [
        completion(
            tool_calls=[
                tool_call(
                    "send_message_to_agent",
                    {"agent_name": "Email to Alice", "instructions": "draft a reply"},
                )
            ]
        ),
        completion(tool_calls=[tool_call("send_message_to_user", {"message": "On it."})]),
        completion(""),
    ]

    result, fake = await _run(scripted_llm, responses, stub_dispatched_agents)

    fake.assert_drained()
    assert result.success is True
    assert result.execution_agents_used == 1
    assert "Email to Alice" in roster.get_all_names()
    assert stub_dispatched_agents == [("Email to Alice", "draft a reply")]

    logged = [tag for tag, _, _ in execution_logs.iter_entries("Email to Alice")]
    assert "agent_request" in logged


async def test_user_message_is_recorded_before_anything_else(
    scripted_llm, stub_dispatched_agents, conversation_log
) -> None:
    responses = [completion("hello there")]

    await _run(scripted_llm, responses, stub_dispatched_agents, message="say hi")

    entries = list(conversation_log.iter_entries())
    assert entries[0][0] == "user_message"
    assert entries[0][2] == "say hi"
    assert entries[1][0] == "poke_reply"
    assert entries[1][2] == "hello there"


async def test_send_message_to_user_wins_over_raw_text(
    scripted_llm, stub_dispatched_agents, conversation_log
) -> None:
    responses = [
        completion(
            content="internal reasoning that should not surface",
            tool_calls=[tool_call("send_message_to_user", {"message": "The draft is ready."})],
        ),
        completion(""),
    ]

    result, _ = await _run(scripted_llm, responses, stub_dispatched_agents)

    assert result.response == "The draft is ready."
    replies = [payload for tag, _, payload in conversation_log.iter_entries() if tag == "poke_reply"]
    assert replies == ["The draft is ready."]


async def test_malformed_tool_arguments_do_not_crash_the_turn(
    scripted_llm, stub_dispatched_agents, conversation_log
) -> None:
    responses = [
        completion(tool_calls=[tool_call("send_message_to_agent", "{not valid json")]),
        completion(tool_calls=[tool_call("send_message_to_user", {"message": "Retrying safely."})]),
        completion(""),
    ]

    result, fake = await _run(scripted_llm, responses, stub_dispatched_agents)

    fake.assert_drained()
    assert result.success is True
    assert result.response == "Retrying safely."
    assert stub_dispatched_agents == []
    assert "Retrying safely." in [payload for tag, _, payload in conversation_log.iter_entries() if tag == "poke_reply"]


async def test_unknown_tool_is_reported_back_to_the_model(
    scripted_llm, stub_dispatched_agents
) -> None:
    responses = [
        completion(tool_calls=[tool_call("delete_everything", {})]),
        completion("I could not do that."),
    ]

    result, fake = await _run(scripted_llm, responses, stub_dispatched_agents)

    fake.assert_drained()
    assert result.success is True
    assert result.response == "I could not do that."


async def test_iteration_limit_produces_a_visible_failure(
    scripted_llm, stub_dispatched_agents, conversation_log
) -> None:
    """Regression: the cap must never leave the user with an empty chat."""
    cap = interaction_runtime.InteractionAgentRuntime.MAX_TOOL_ITERATIONS
    responses = [completion(tool_calls=[tool_call("wait", {"reason": "idle"})])] * cap

    result, fake = await _run(scripted_llm, responses, stub_dispatched_agents)

    fake.assert_drained()
    assert result.success is False
    replies = [payload for tag, _, payload in conversation_log.iter_entries() if tag == "poke_reply"]
    assert replies, "a failure reply must be recorded so the UI is not silent"
    assert "couldn't complete" in replies[-1]


async def test_wait_loop_stops_once_work_is_in_flight(
    scripted_llm, stub_dispatched_agents, conversation_log
) -> None:
    """Regression: polling with wait must not burn the iteration cap or fake an error."""
    responses = [
        completion(
            tool_calls=[
                tool_call(
                    "send_message_to_agent",
                    {"agent_name": "Email Summary Agent", "instructions": "summarize"},
                )
            ]
        ),
        completion(tool_calls=[tool_call("wait", {"reason": "waiting for agent"})]),
        completion(tool_calls=[tool_call("wait", {"reason": "still waiting"})]),
    ]

    result, fake = await _run(scripted_llm, responses, stub_dispatched_agents)

    assert fake.remaining == 1, "the loop should exit after the first in-flight wait"
    assert result.success is True
    replies = [payload for tag, _, payload in conversation_log.iter_entries() if tag == "poke_reply"]
    assert not any("couldn't complete" in reply for reply in replies)


async def test_rate_limit_failure_mentions_the_daily_limit(
    scripted_llm, stub_dispatched_agents, conversation_log
) -> None:
    responses = [
        OpenRouterError("OpenRouter request failed (429): free-models-per-day limit reached")
    ]

    result, _ = await _run(scripted_llm, responses, stub_dispatched_agents)

    assert result.success is False
    replies = [payload for tag, _, payload in conversation_log.iter_entries() if tag == "poke_reply"]
    assert "daily limit" in replies[-1]
    assert "couldn't complete" not in replies[-1]


async def test_missing_configuration_reports_clearly(
    scripted_llm, stub_dispatched_agents, monkeypatch: pytest.MonkeyPatch
) -> None:
    from server.config import Settings

    # Settings defaults are captured at import, so patch the resolved settings object
    monkeypatch.setattr(interaction_runtime, "get_settings", lambda: Settings(openrouter_api_key=None))

    with pytest.raises(ValueError, match="OpenRouter API key not configured"):
        interaction_runtime.InteractionAgentRuntime()
