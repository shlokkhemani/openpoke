"""Model client: local-endpoint defaults, optional credentials, reasoning fallback."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from server.config import Settings, get_settings
from server.llm_client import client as llm_client


class _RecordingClient:
    """Stand-in for ``httpx.AsyncClient`` that captures the outgoing request."""

    requests: List[Dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_RecordingClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def post(self, url: str, *, headers=None, json=None, timeout=None):
        type(self).requests.append(
            {"url": url, "headers": dict(headers or {}), "json": json, "timeout": timeout}
        )
        return _FakeResponse()


class _FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Dict[str, Any]:
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> List[Dict[str, Any]]:
    """Route client calls to a recorder instead of the network."""
    _RecordingClient.requests = []
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", _RecordingClient)
    return _RecordingClient.requests


async def test_no_api_key_is_required(recorded, monkeypatch: pytest.MonkeyPatch) -> None:
    """A local llama-server needs no credentials, so no auth header is sent."""
    monkeypatch.setattr(llm_client, "get_settings", lambda: Settings(llm_api_key=None))

    await llm_client.request_chat_completion(
        model="swift", messages=[{"role": "user", "content": "hi"}]
    )

    assert len(recorded) == 1
    assert "Authorization" not in recorded[0]["headers"]


async def test_api_key_is_sent_when_configured(recorded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client, "get_settings", lambda: Settings(llm_api_key="secret"))

    await llm_client.request_chat_completion(
        model="swift", messages=[{"role": "user", "content": "hi"}]
    )

    assert recorded[0]["headers"]["Authorization"] == "Bearer secret"


async def test_base_url_and_timeout_come_from_settings(recorded) -> None:
    """Settings must drive the endpoint, so no call site hardcodes one."""
    settings = get_settings()

    await llm_client.request_chat_completion(
        model="swift", messages=[{"role": "user", "content": "hi"}]
    )

    assert recorded[0]["url"] == f"{settings.llm_base_url}/chat/completions"
    assert recorded[0]["timeout"] == float(settings.llm_timeout_seconds)


async def test_explicit_base_url_overrides_settings(recorded) -> None:
    await llm_client.request_chat_completion(
        model="swift",
        messages=[{"role": "user", "content": "hi"}],
        base_url="http://127.0.0.1:9999/v1/",
    )

    assert recorded[0]["url"] == "http://127.0.0.1:9999/v1/chat/completions"


def test_blank_base_url_fails_with_actionable_message() -> None:
    with pytest.raises(llm_client.LLMError, match="LLM_BASE_URL"):
        llm_client._resolve_base_url("   ")


def test_defaults_target_the_local_qwen_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENPOKE_MODEL", raising=False)
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    settings = Settings()

    assert settings.llm_base_url == "http://127.0.0.1:8080/v1"
    assert settings.llm_model == "Qwen3.5-9B-Q4_K_M"
    assert settings.llm_timeout_seconds == 300
    assert settings.llm_api_key is None


def test_every_agent_uses_the_single_model_setting() -> None:
    settings = get_settings()

    assert settings.interaction_agent_model == settings.llm_model
    assert settings.execution_agent_model == settings.llm_model
    assert settings.execution_agent_search_model == settings.llm_model
    assert settings.summarizer_model == settings.llm_model
    assert settings.email_classifier_model == settings.llm_model


def test_openpoke_model_remains_an_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("OPENPOKE_MODEL", "legacy/model")

    assert Settings().llm_model == "legacy/model"


def test_reasoning_content_is_used_when_content_is_blank() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "The user needs no reply.",
                }
            }
        ]
    }

    message = llm_client.extract_assistant_message(response)

    assert message["content"] == "The user needs no reply."


def test_reasoning_is_ignored_when_a_tool_call_exists() -> None:
    """Promoting reasoning must not fabricate prose alongside a tool call."""
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "I should call the wait tool.",
                    "tool_calls": [
                        {"id": "call_1", "function": {"name": "wait", "arguments": "{}"}}
                    ],
                }
            }
        ]
    }

    message = llm_client.extract_assistant_message(response)

    assert message["content"] == ""
    assert message["tool_calls"]


def test_content_wins_over_reasoning() -> None:
    response = {
        "choices": [
            {"message": {"role": "assistant", "content": "Final answer.", "reasoning_content": "th"}}
        ]
    }

    assert llm_client.extract_assistant_message(response)["content"] == "Final answer."


def test_missing_message_raises() -> None:
    with pytest.raises(llm_client.LLMError, match="assistant message"):
        llm_client.extract_assistant_message({"choices": []})


async def test_connection_failure_is_distinguishable(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead server must be classifiable so the UI can say something useful."""

    class _RefusingClient(_RecordingClient):
        async def post(self, url: str, **kwargs: Any):
            raise llm_client.httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", _RefusingClient)

    with pytest.raises(llm_client.LLMConnectionError, match="llama-server"):
        await llm_client.request_chat_completion(
            model="swift", messages=[{"role": "user", "content": "hi"}]
        )


async def test_read_timeout_is_distinguishable(monkeypatch: pytest.MonkeyPatch) -> None:
    class _SlowClient(_RecordingClient):
        async def post(self, url: str, **kwargs: Any):
            raise llm_client.httpx.ReadTimeout("too slow")

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", _SlowClient)

    with pytest.raises(llm_client.LLMTimeoutError, match="timed out"):
        await llm_client.request_chat_completion(
            model="swift", messages=[{"role": "user", "content": "hi"}]
        )
