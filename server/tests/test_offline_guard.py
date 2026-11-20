"""Guard test: the offline harness must actually block real network calls."""

from __future__ import annotations

import httpx
import pytest

from server.llm_client import request_chat_completion


async def test_real_http_call_is_blocked() -> None:
    """If the guard regressed, this would reach the model server for real."""
    with pytest.raises(AssertionError, match="Network access is disabled"):
        await request_chat_completion(
            model="test/model",
            messages=[{"role": "user", "content": "ping"}],
            base_url="http://127.0.0.1:8080/v1",
        )


async def test_transport_layer_is_patched() -> None:
    """Assert the patch is applied at the transport, not merely at a helper."""
    transport = httpx.AsyncHTTPTransport()

    with pytest.raises(AssertionError, match="Network access is disabled"):
        await transport.handle_async_request(httpx.Request("POST", "http://127.0.0.1:8080/v1"))
