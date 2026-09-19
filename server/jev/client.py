"""Thin async wrapper around TypeSafe's System One API (the Jev model).

The whole layer is optional. Without ``TYPESAFE_API_KEY`` — or without the
``typesafe-sdk`` package installed — :func:`is_enabled` returns ``False`` and
every caller keeps its pre-Jev behaviour.

Failure policy is **fail-open**: :func:`ask` never raises and never blocks a
caller. A Jev outage degrades OpenPoke to exactly what it did before this layer
existed, which is the right trade for classification and advisory guardrails.
TypeSafe does not publish guidance either way, so this is our choice and it is
stated here rather than buried at the call sites.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Mapping, Optional

from ..config import get_settings
from ..logging_config import logger

try:  # pragma: no cover - exercised by the import-guard test
    from typesafe_sdk import (
        AsyncTypeSafeClient,
        RetryPolicy,
        SystemOneResponse,
        TypeSafeAPIError,
        TypeSafeError,
    )

    SDK_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    # Deliberately broader than ImportError: a dependency conflict inside the
    # SDK (it needs pydantic>=2.12 while the server only pins >=2.7) raises
    # something else entirely, and it must not stop the server booting for
    # users who never configured Jev.
    AsyncTypeSafeClient = None  # type: ignore[assignment]
    RetryPolicy = None  # type: ignore[assignment]
    SystemOneResponse = None  # type: ignore[assignment]
    TypeSafeAPIError = ()  # type: ignore[assignment]
    TypeSafeError = ()  # type: ignore[assignment]
    SDK_AVAILABLE = False


_client: Optional[Any] = None
# A plain threading lock, not an asyncio one: an ``asyncio.Lock`` built at
# import time binds to whichever loop first contends for it, and releasing it
# from another loop's thread never wakes the waiter. Construction below is
# synchronous, so there is nothing to await while holding this.
_client_lock = threading.Lock()


# Report whether typed decisions are configured and usable in this process
def is_enabled() -> bool:
    """Return ``True`` when Jev is installed and an API key is configured."""

    if not SDK_AVAILABLE:
        return False
    return get_settings().jev_enabled


# Build (once) the shared async client used for every typed decision
async def get_client() -> Optional[Any]:
    """Return the process-wide client, or ``None`` when Jev is not configured."""

    global _client

    if not is_enabled():
        return None
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client
        settings = get_settings()
        extra: Dict[str, Any] = {}
        if settings.typesafe_base_url:
            # Routing through a gateway (Vercel's AI Gateway, Neon's, a company
            # proxy) is a supported deployment: the SDK appends `/v1/systemone`
            # to whatever origin it is given. Passed explicitly rather than left
            # to the SDK's own env var so the setting is visible in the code.
            extra["base_url"] = settings.typesafe_base_url
        try:
            _client = AsyncTypeSafeClient(
                api_key=settings.typesafe_api_key,
                # Pinned, never an alias: an alias moves when a release ships
                # and the thresholds in jev/thresholds.py are calibrated
                # against one specific model. https://docs.typesafe.ai/models
                model=settings.jev_model,
                timeout=settings.jev_timeout_seconds,
                retry=RetryPolicy(
                    max_retries=settings.jev_max_retries,
                    timeout=settings.jev_retry_budget_seconds,
                ),
                **extra,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Jev client could not be created; typed decisions disabled",
                extra={"error": str(exc)},
            )
            return None
    return _client


# Tear down the shared client (used on shutdown and between tests)
async def close_client() -> None:
    """Release the shared client's network resources."""

    global _client

    client = _client
    _client = None
    if client is None:
        return
    try:
        await client.aclose()
    except Exception:  # pragma: no cover - defensive
        logger.debug("Ignoring error while closing the Jev client")


# Replace the shared client, for tests that inject a mock transport
def set_client(client: Optional[Any]) -> None:
    """Install a client instance directly. Intended for tests."""

    global _client
    _client = client


# Ask Jev a batch of typed questions about one piece of state
async def ask(
    *,
    state: Any,
    questions: Mapping[str, Dict[str, Any]],
    purpose: str,
    deadline: Optional[float] = None,
) -> Optional[Any]:
    """Return a ``SystemOneResponse``, or ``None`` if the decision is unavailable.

    Every question about the same state belongs in a single call: the state is
    billed once, questions are evaluated in parallel, and output tokens are
    free, so extra questions cost almost nothing and add almost no latency.
    https://docs.typesafe.ai/cookbooks/parallel_questions

    ``deadline`` bounds the **wall-clock** time this call may take, including
    retries and backoff. The SDK's own retry budget does not: it decides
    whether to sleep again before sleeping, so the last attempt still gets a
    full per-request timeout on top. Since these calls sit inside a sequential
    watcher loop and inside an agent loop with a 90s cap, an unbounded wait
    would turn one Jev outage into a user-visible timeout.
    """

    if not questions:
        return None

    client = await get_client()
    if client is None:
        return None

    if deadline is None:
        deadline = get_settings().jev_deadline_seconds

    try:
        response = await asyncio.wait_for(
            client.system_one(state=state, questions=dict(questions)),
            timeout=deadline if deadline and deadline > 0 else None,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Jev request exceeded its deadline",
            extra={"purpose": purpose, "deadline": deadline},
        )
        return None
    except TypeSafeAPIError as exc:  # type: ignore[misc]
        logger.warning(
            "Jev request failed",
            extra={
                "purpose": purpose,
                "status": getattr(exc, "status", None),
                "request_id": request_id(exc),
                "error": str(exc),
            },
        )
        return None
    except TypeSafeError as exc:  # type: ignore[misc]
        logger.warning(
            "Jev request failed",
            extra={"purpose": purpose, "error": str(exc)},
        )
        return None
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "Unexpected error during a Jev request",
            extra={"purpose": purpose, "error": str(exc)},
        )
        return None

    logger.debug(
        "Jev decision complete",
        extra={
            "purpose": purpose,
            "model": getattr(response, "model", None),
            "request_id": request_id(response),
            "questions": len(questions),
        },
    )
    return response


# Read a response's request id without trusting the accessor not to raise
def request_id(response: Any) -> Optional[str]:
    """Return the ``x-typesafe-request-id`` value, or ``None``.

    ``SystemOneResponse.request_id`` is a ``cached_property`` that *raises*
    when the header is missing, and ``getattr`` with a default only swallows
    ``AttributeError``. A proxy that strips the header would otherwise take
    down the caller from the success path.
    """

    try:
        value = getattr(response, "request_id", None)
    except Exception:
        return None
    return value if isinstance(value, str) else None


# Read one noul probability out of a response without trusting its shape
def noul(response: Any, key: str) -> Optional[float]:
    """Return the probability for noul ``key``, or ``None`` when absent.

    Answers are read defensively on purpose. A question that was dropped, a
    model upgrade that changes an answer's type, and a malformed payload all
    have to degrade to "no opinion" rather than raise inside a watcher loop.
    """

    if response is None:
        return None
    answers = getattr(response, "answers", None)
    if not isinstance(answers, Mapping):
        return None
    answer = answers.get(key)
    value = getattr(answer, "noul", None)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    numeric = float(value)
    if numeric != numeric or not 0.0 <= numeric <= 1.0:  # NaN or out of range
        return None
    return numeric


__all__ = [
    "SDK_AVAILABLE",
    "ask",
    "request_id",
    "close_client",
    "get_client",
    "is_enabled",
    "noul",
    "set_client",
]
