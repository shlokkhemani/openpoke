"""Shared pytest fixtures.

Every test runs against temporary data directories. The application builds its
stores as module-level singletons at import time, so the fixtures below rebuild
those singletons against ``tmp_path`` instead of the real ``server/data``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

import pytest

from server.agents.execution_agent.tools import gmail as gmail_tools
from server.agents.execution_agent.tools import triggers as trigger_tools
from server.agents.execution_agent.tasks.search_email import tool as email_search_tool
from server.config import get_settings
from server.services import triggers as triggers_package
from server.services.conversation import log as conversation_log_module
from server.services.conversation.log import ConversationLog
from server.services.execution import log_store as log_store_module
from server.services.execution import roster as roster_module


def _response(content: str = "", tool_calls: Optional[List[dict]] = None) -> dict:
    """Build an OpenAI-shaped completion response."""
    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message, "finish_reason": "stop"}]}


def tool_call(name: str, arguments: Any = None, call_id: str = "call_1") -> dict:
    """Build an OpenAI-shaped tool call.

    ``arguments`` may be a dict, a JSON string, or raw invalid JSON text.
    """
    if isinstance(arguments, (dict, list)):
        payload = json.dumps(arguments)
    elif arguments is None:
        payload = "{}"
    else:
        payload = str(arguments)
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": payload},
    }


def completion(content: str = "", tool_calls: Optional[List[dict]] = None) -> dict:
    """Public alias for a stubbed completion response."""
    return _response(content=content, tool_calls=tool_calls)


class ScriptedLLM:
    """Queue of canned responses for ``request_chat_completion``."""

    def __init__(self, responses: Iterable[Any]):
        self._responses: List[Any] = list(responses)
        self.calls: List[dict] = []

    async def __call__(self, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError(
                f"Unexpected extra model call (#{len(self.calls)}); the scripted queue was empty."
            )
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    @property
    def remaining(self) -> int:
        return len(self._responses)

    def assert_drained(self) -> None:
        assert self.remaining == 0, f"{self.remaining} scripted response(s) were never used"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch):
    """Fail loudly if a test tries to reach the real network.

    Patched at the HTTP transport layer so it does not interfere with the
    event loop, which uses sockets internally on Windows.
    """
    import httpx

    def _blocked_sync(*args: Any, **kwargs: Any):
        raise AssertionError("Network access is disabled in tests; stub the model boundary instead.")

    async def _blocked_async(*args: Any, **kwargs: Any):
        raise AssertionError("Network access is disabled in tests; stub the model boundary instead.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked_sync)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _blocked_async)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Isolated data directory for one test."""
    root = tmp_path / "data"
    (root / "conversation").mkdir(parents=True, exist_ok=True)
    (root / "execution_agents").mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(autouse=True)
def isolated_stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data_dir: Path):
    """Rebind every module-level store singleton onto the temporary directory."""
    get_settings.cache_clear()

    # Conversation log plus its working-memory companion
    conversation_log = ConversationLog(data_dir / "conversation" / "poke_conversation.log")
    monkeypatch.setattr(conversation_log_module, "_conversation_log", conversation_log)

    from server.services.conversation.summarization import working_memory_log as working_memory_module

    working_memory = working_memory_module.WorkingMemoryLog(
        data_dir / "conversation" / "poke_working_memory.log"
    )
    monkeypatch.setattr(working_memory_module, "_working_memory_log", working_memory)

    # Execution agent roster and per-agent logs
    roster = roster_module.AgentRoster(data_dir / "execution_agents" / "roster.json")
    monkeypatch.setattr(roster_module, "_agent_roster", roster)

    execution_logs = log_store_module.ExecutionAgentLogStore(data_dir / "execution_agents")
    monkeypatch.setattr(log_store_module, "_execution_agent_logs", execution_logs)

    # Tools capture the log store and trigger service at import time
    monkeypatch.setattr(gmail_tools, "_LOG_STORE", execution_logs)
    monkeypatch.setattr(email_search_tool, "_LOG_STORE", execution_logs)

    trigger_store = triggers_package.TriggerStore(tmp_path / "data" / "triggers.db")
    trigger_service = triggers_package.TriggerService(trigger_store)
    monkeypatch.setattr(triggers_package, "_trigger_store", trigger_store)
    monkeypatch.setattr(triggers_package, "_trigger_service", trigger_service)
    monkeypatch.setattr(trigger_tools, "_LOG_STORE", execution_logs)
    monkeypatch.setattr(trigger_tools, "_TRIGGER_SERVICE", trigger_service)

    # No API key is required for a local llama-server, only a base URL
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("LLM_MODEL", "test/model")
    get_settings.cache_clear()

    yield

    get_settings.cache_clear()


@pytest.fixture
def scripted_llm(monkeypatch: pytest.MonkeyPatch) -> Callable[..., ScriptedLLM]:
    """Patch the model boundary in the module under test.

    Usage: ``scripted = scripted_llm(interaction_runtime, [completion("hi")])``.
    """

    def _install(module: Any, responses: Iterable[Any]) -> ScriptedLLM:
        fake = ScriptedLLM(responses)
        monkeypatch.setattr(module, "request_chat_completion", fake)
        return fake

    return _install


@pytest.fixture
def conversation_log():
    """The isolated conversation log for the current test."""
    return conversation_log_module.get_conversation_log()


@pytest.fixture
def roster():
    """The isolated agent roster for the current test."""
    return roster_module.get_agent_roster()


@pytest.fixture
def execution_logs():
    """The isolated execution agent log store for the current test."""
    return log_store_module.get_execution_agent_logs()
