"""Shared fixtures for the typed-decision tests.

``server.config.Settings`` reads the environment once at class-definition time
and ``get_settings`` is ``lru_cache``d, so every test that changes an env var
has to clear that cache *and* rebuild the field defaults. ``reload_settings``
does both.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Mapping

import httpx2
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import config as config_module  # noqa: E402
from server.jev import client as jev_client  # noqa: E402
from server.jev import decision_log as jev_decision_log  # noqa: E402


@pytest.fixture(autouse=True)
def reload_settings() -> Iterator[Callable[[], None]]:
    """Reset cached settings before and after every test."""

    def _reload() -> None:
        importlib.reload(config_module)
        config_module.get_settings.cache_clear()
        # `Settings` snapshots the environment at class-definition time, so a
        # reload is the only way to pick up a monkeypatched env var. Every
        # module that did `from ...config import get_settings` still holds the
        # pre-reload accessor, whose cache we cannot reach, so rebind them all.
        for name, module in list(sys.modules.items()):
            if not name.startswith("server"):
                continue
            if getattr(module, "get_settings", None) is not None:
                module.get_settings = config_module.get_settings  # type: ignore[attr-defined]

    _reload()
    yield _reload
    jev_client.set_client(None)
    jev_decision_log.set_decision_log(None)
    _reload()


@pytest.fixture(autouse=True)
def isolated_decision_log(tmp_path: Path) -> Iterator[Any]:
    """Point the decision log at a temp file so tests never touch server/data."""

    log = jev_decision_log.DecisionLog(tmp_path / "jev_decisions.jsonl")
    jev_decision_log.set_decision_log(log)
    yield log
    jev_decision_log.set_decision_log(None)


@pytest.fixture
def jev_env(monkeypatch: pytest.MonkeyPatch, reload_settings: Callable[[], None]) -> None:
    """Configure the process as if Jev were enabled."""

    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    monkeypatch.setenv("JEV_MODEL", "jev-1.13.0")
    reload_settings()


@pytest.fixture
def jev_transport() -> Callable[..., Any]:
    """Return a factory installing a real SDK client over a mock transport.

    Using the SDK's documented ``transport`` seam rather than a hand-written
    double means the tests exercise the SDK's own request serialisation and
    response validation, so a malformed question dict or a renamed answer field
    fails here instead of in production.
    """

    from typesafe_sdk import AsyncTypeSafeClient

    calls: list[Dict[str, Any]] = []

    def install(
        answers: Mapping[str, Any] | Callable[[Mapping[str, Any]], Mapping[str, Any]],
        *,
        status: int = 200,
        body: Any = None,
    ) -> list[Dict[str, Any]]:
        def handler(request: httpx2.Request) -> httpx2.Response:
            payload = json.loads(request.content)
            calls.append(payload)
            if status != 200:
                return httpx2.Response(status, json=body if body is not None else {"error": "boom"})
            resolved = answers(payload) if callable(answers) else answers
            if body is not None:
                return httpx2.Response(status, json=body)
            return httpx2.Response(
                status,
                json={
                    "model": "jev-1.13.0",
                    "usage": {"input_tokens": 12, "output_tokens": 0},
                    "answers": dict(resolved),
                },
                headers={"x-typesafe-request-id": "req_test"},
            )

        jev_client.set_client(
            AsyncTypeSafeClient(
                api_key="sk-test",
                model="jev-1.13.0",
                transport=httpx2.MockTransport(handler),
            )
        )
        return calls

    return install


def noul_answers(**values: float) -> Dict[str, Dict[str, Any]]:
    """Build a ``answers`` payload of noul probabilities."""

    return {key: {"type": "noul", "noul": value} for key, value in values.items()}
