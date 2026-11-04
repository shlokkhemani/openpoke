"""Track background interaction turns for benchmark synchronization."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator, Optional


class InteractionActivity:
    def __init__(self) -> None:
        self._active = 0
        self._failures: list[str] = []
        self._lock = threading.Lock()

    @contextmanager
    def track(self) -> Iterator[None]:
        with self._lock:
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1

    def active_count(self) -> int:
        with self._lock:
            return self._active

    def record_failure(self, reason: Optional[str] = None) -> None:
        with self._lock:
            self._failures.append((reason or "unknown failure").strip())

    def failure_count(self) -> int:
        with self._lock:
            return len(self._failures)

    def failures(self) -> list[str]:
        with self._lock:
            return list(self._failures)

    def reset_failures(self) -> None:
        with self._lock:
            self._failures = []


_interaction_activity = InteractionActivity()


def get_interaction_activity() -> InteractionActivity:
    return _interaction_activity


__all__ = ["InteractionActivity", "get_interaction_activity"]
