"""Durable email-tool evidence for inspecting benchmark outcomes."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from .data_paths import get_data_dir

_LOCK = threading.Lock()


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

