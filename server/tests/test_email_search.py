"""Email search: local model endpoint gating and reasoning fallback."""

from __future__ import annotations

import pytest

from server.agents.execution_agent.tasks.search_email import tool as email_tool
from server.config import Settings
from server.tests.conftest import completion, tool_call


@pytest.fixture
def gmail_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_tool, "get_active_gmail_user_id", lambda: "user-123")


async def test_search_runs_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch, gmail_connected
) -> None:
    """A local llama-server has no key; search must not be disabled because of it."""
    settings = Settings(llm_api_key=None)
    monkeypatch.setattr(email_tool, "get_settings", lambda: settings)

    calls: list[dict] = []

    async def _fake_completion(**kwargs):
        calls.append(kwargs)
        return completion(tool_calls=[tool_call(email_tool.COMPLETE_TOOL_NAME, {"message_ids": []})])

    monkeypatch.setattr(email_tool, "request_chat_completion", _fake_completion)

    result = await email_tool.task_email_search("anything from alice")

    assert not isinstance(result, dict), "a dict means the tool returned an error payload"
    assert result == []
    assert calls[0]["base_url"] == settings.llm_base_url
    assert "api_key" not in calls[0]


async def test_missing_base_url_disables_search_with_clear_message(
    monkeypatch: pytest.MonkeyPatch, gmail_connected
) -> None:
    monkeypatch.setattr(email_tool, "get_settings", lambda: Settings(llm_base_url=""))

    result = await email_tool.task_email_search("anything")

    assert result == {"error": email_tool.ERROR_LLM_NOT_CONFIGURED}
    assert "LLM_BASE_URL" in email_tool.ERROR_LLM_NOT_CONFIGURED


async def test_reasoning_only_reply_is_treated_as_a_finished_turn(
    monkeypatch: pytest.MonkeyPatch, gmail_connected
) -> None:
    """A blank content with populated reasoning must not look like an empty reply."""
    reasoning_only = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "No matching emails were needed.",
                }
            }
        ]
    }

    calls: list[dict] = []

    async def _fake_completion(**kwargs):
        calls.append(kwargs)
        return reasoning_only

    monkeypatch.setattr(email_tool, "request_chat_completion", _fake_completion)

    result = await email_tool.task_email_search("nothing")

    assert len(calls) == 1, "the turn should end instead of looping on an empty message"
    assert result == []
