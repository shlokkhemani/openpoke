from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Sequence, Union

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

    # Saved smoke traces contain responses taking longer than 60 seconds.
    # Wait longer in benchmark mode rather than retrying an uncertain paid call
    # prematurely.
    timeout = 60.0
    if get_settings().benchmark_mode:
        read_timeout = float(os.getenv("OPENPOKE_BENCHMARK_MODEL_READ_TIMEOUT", "180"))
        if not 0 < read_timeout < float("inf"):
            raise ValueError("Benchmark model read timeout must be positive and finite")
        timeout = httpx.Timeout(60.0, read=read_timeout)
    async with httpx.AsyncClient() as client:
        for attempt in range(3):
            try:
                response = await client.post(
                    url,
                    headers=_headers(api_key=api_key),
                    json=payload,
                    timeout=timeout,
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


async def request_embeddings(*, model: str, input: Union[str, Sequence[str]],
                             api_key: Optional[str] = None,
                             base_url: str = OpenRouterBaseURL) -> Dict[str, Any]:
    """Request embeddings for roster matching; no retries."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{base_url.rstrip('/')}/embeddings",
                                         headers=_headers(api_key=api_key),
                                         json={"model": model,
                                               "input": input if isinstance(input, str) else list(input),
                                               "encoding_format": "float"},
                                         timeout=60.0)
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OpenRouterError("Embedding request failed") from exc
    return result


__all__ = ["OpenRouterError", "request_chat_completion", "request_embeddings", "OpenRouterBaseURL"]
