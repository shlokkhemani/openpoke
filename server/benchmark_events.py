"""Durable benchmark email evidence and scoped input-token counts."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from .data_paths import get_data_dir

_LOCK = threading.Lock()


def record_input_tokens(kind: str, model: str, response: Any = None, *,
                        http_status: int | None = None, error_type: str | None = None,
                        request_outcome: str | None = None) -> None:
    """Record provider input usage, never guesses, outputs, prompts or vectors."""
    if kind not in {"interaction", "embedding"}:
        raise ValueError("Unsupported token scope")
    payload = response if isinstance(response, dict) else {}
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    fields = ("prompt_tokens", "input_tokens", "total_tokens") if kind == "embedding" else ("prompt_tokens", "input_tokens")
    tokens = next((usage[field] for field in fields
                   if isinstance(usage.get(field), int) and not isinstance(usage[field], bool)
                   and usage[field] >= 0), None)
    if request_outcome is None:
        request_outcome = "success" if isinstance(response, dict) else "unknown"
    append_event({"event": "input_tokens", "kind": kind, "model": model,
                  "input_tokens": tokens, "response_id": payload.get("id"),
                  "request_outcome": request_outcome, "http_status": http_status,
                  "error_type": error_type,
                  "usage_status": "recorded" if tokens is not None else "missing_or_invalid",
                  "input_usage": {field: usage[field] for field in fields if field in usage}})


def append_event(event: dict[str, Any]) -> None:
    if os.getenv("OPENPOKE_BENCHMARK_MODE", "").lower() not in {"1", "true", "yes", "on"}:
        return
    path = get_data_dir() / "benchmark_events.jsonl"
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(path: Path | None = None) -> list[dict]:
    path = path or get_data_dir() / "benchmark_events.jsonl"
    with _LOCK:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
