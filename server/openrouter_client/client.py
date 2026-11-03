from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx

from ..config import get_settings

OpenRouterBaseURL = "https://openrouter.ai/api/v1"


class OpenRouterError(RuntimeError):
    """Raised when the OpenRouter API returns an error response."""


def _headers(*, api_key: Optional[str] = None) -> Dict[str, str]:
    settings = get_settings()
    key = (api_key or settings.openrouter_api_key or "").strip()
    if not key:
        raise OpenRouterError("Missing OpenRouter API key")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    return headers


def _build_messages(messages: List[Dict[str, str]], system: Optional[str]) -> List[Dict[str, str]]:
    if system:
        return [{"role": "system", "content": system}, *messages]
    return messages


def _handle_response_error(exc: httpx.HTTPStatusError) -> None:
    response = exc.response
    detail: str
    try:
        payload = response.json()
        detail = payload.get("error") or payload.get("message") or json.dumps(payload)
    except Exception:
        detail = response.text
    raise OpenRouterError(f"OpenRouter request failed ({response.status_code}): {detail}") from exc


async def request_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    api_key: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    base_url: str = OpenRouterBaseURL,
) -> Dict[str, Any]:
    """Request a chat completion and return the raw JSON payload."""

    payload: Dict[str, object] = {
        "model": model,
        "messages": _build_messages(messages, system),
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    url = f"{base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient() as client:
        for attempt in range(3):
            try:
                response = await client.post(
                    url,
                    headers=_headers(api_key=api_key),
                    json=payload,
                    timeout=60.0,
                )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    _handle_response_error(exc)
                return response.json()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - handled above
                _handle_response_error(exc)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise OpenRouterError(
                        f"OpenRouter request failed after 3 attempts: {exc}"
                    ) from exc
                await asyncio.sleep(2**attempt)

    raise OpenRouterError("OpenRouter request failed: unknown error")


__all__ = ["OpenRouterError", "request_chat_completion", "OpenRouterBaseURL"]
