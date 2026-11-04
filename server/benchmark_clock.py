"""A controllable clock used only by isolated benchmark servers."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone


class BenchmarkClock:
    def __init__(self) -> None:
        self._day = 0
        self._lock = threading.Lock()
        raw_start = os.getenv("OPENPOKE_BENCHMARK_START_TIME", "2026-01-01T09:00:00+00:00")
        try:
            start = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
        except ValueError:
            start = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        self._start = start.astimezone(timezone.utc)

    def set_day(self, day: int) -> None:
        if day < 0:
            raise ValueError("benchmark day cannot be negative")
        with self._lock:
            if day < self._day:
                raise ValueError("benchmark day cannot move backwards")
            self._day = day

    def reset(self) -> None:
        with self._lock:
            self._day = 0

    def day(self) -> int:
        with self._lock:
            return self._day

    def now_utc(self) -> datetime:
        with self._lock:
            return self._start + timedelta(days=self._day)


_benchmark_clock = BenchmarkClock()


def benchmark_clock_enabled() -> bool:
    return os.getenv("OPENPOKE_BENCHMARK_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_benchmark_clock() -> BenchmarkClock:
    return _benchmark_clock


__all__ = ["BenchmarkClock", "benchmark_clock_enabled", "get_benchmark_clock"]
