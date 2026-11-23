"""OpenAI-compatible chat completion client.

Works against any server that speaks the OpenAI ``/chat/completions`` shape.
The default target is a local ``llama-server`` (llama.cpp), which needs no API
key and can be slow enough that the timeout has to be configurable.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from ..config import get_settings


DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"


class LLMError(RuntimeError):
    """Raised when the model server cannot be reached or returns an error."""


class LLMConnectionError(LLMError):
    """Raised when the model server is not reachable at the configured base URL."""


class LLMTimeoutError(LLMError):
    """Raised when the model server does not answer within the timeout."""


def _resolve_base_url(base_url: Optional[str]) -> str:
    """Return the configured base URL, failing clearly when it is unset."""

    resolved = (base_url or get_settings().llm_base_url or "").strip()
    if not resolved:
        raise LLMError(
            "No model endpoint configured. Set LLM_BASE_URL to your local llama-server, "
            "for example http://127.0.0.1:8080/v1"
        )
    return resolved


def _resolve_timeout(timeout: Optional[float]) -> float:
    """Return the request timeout in seconds, from settings when not given."""

    if timeout is not None:
        return timeout
    return float(get_settings().llm_timeout_seconds)


def _headers(*, api_key: Optional[str] = None) -> Dict[str, str]:
    """Build request headers. Local servers need no credentials."""

    settings = get_settings()
    key = (api_key or settings.llm_api_key or "").strip()

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"

    return headers


def _build_messages(messages: List[Dict[str, str]], system: Optional[str]) -> List[Dict[str, str]]:
    if system:
        return [{"role": "system", "content": system}, *messages]
    return messages


def _response_detail(payload: Any) -> Optional[str]:
    """Pull a human-readable message out of an error payload."""

    if not isinstance(payload, dict):
        return None

    for key in ("error", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("message")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _handle_response_error(exc: httpx.HTTPStatusError) -> None:
    response = exc.response
    detail: str
    try:
        payload = response.json()
        detail = _response_detail(payload) or json.dumps(payload)
    except Exception:
        detail = response.text
    raise LLMError(f"Model request failed ({response.status_code}): {detail}") from exc


def _note_context(label: str, response: Dict[str, Any]) -> None:
    """Check token usage against the context window and log near-limit notices."""
    from ..services.context_monitor import observe, report_from_usage

    report = report_from_usage(label, response.get("usage"))
    if report is not None:
        observe(report)


def extract_assistant_message(response: Dict[str, Any]) -> Dict[str, Any]:
    """Return the assistant message, tolerating reasoning-only replies.

    Reasoning models (Qwen3 and friends) can emit their whole answer in
    ``reasoning_content`` with an empty ``content``. Every agent loop reads
    ``content``, so an empty string there silently ends a turn. When the model
    produced no tool call, the reasoning text is the best available answer and
    is promoted into ``content``.
    """

    choices = response.get("choices") or []
    message = (choices[0] if choices else {}).get("message")
    if not isinstance(message, dict):
        raise LLMError("Model response did not include an assistant message")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        reasoning = message.get("reasoning_content")
        tool_calls = message.get("tool_calls") or []
        if not tool_calls and isinstance(reasoning, str) and reasoning.strip():
            message = {**message, "content": reasoning.strip()}

    return message


def assistant_text(message: Dict[str, Any]) -> str:
    """Return the trimmed text of an assistant message."""

    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


async def request_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    api_key: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    context_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Request a chat completion and return the raw JSON payload.

    When ``context_label`` is set, the response's token usage is checked against
    the configured context window and a notice is emitted near the limit.
    """

    endpoint = _resolve_base_url(base_url)
    request_timeout = _resolve_timeout(timeout)

    payload: Dict[str, object] = {
        "model": model,
        "messages": _build_messages(messages, system),
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    url = f"{endpoint.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                headers=_headers(api_key=api_key),
                json=payload,
                timeout=request_timeout,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _handle_response_error(exc)
            data = response.json()
            if context_label:
                _note_context(context_label, data)
            return data
        except httpx.HTTPStatusError as exc:  # pragma: no cover - handled above
            _handle_response_error(exc)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Model request to {endpoint} timed out after {request_timeout:.0f}s"
            ) from exc
        except httpx.ConnectError as exc:
            raise LLMConnectionError(
                f"Could not connect to {endpoint}. Is llama-server running?"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Model request to {endpoint} failed: {exc}") from exc

    raise LLMError("Model request failed: unknown error")


__all__ = [
    "DEFAULT_BASE_URL",
    "LLMConnectionError",
    "LLMError",
    "LLMTimeoutError",
    "assistant_text",
    "extract_assistant_message",
    "request_chat_completion",
]
