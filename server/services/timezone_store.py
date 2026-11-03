"""Persist and expose the user's preferred timezone."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..logging_config import logger
from ..data_paths import get_data_dir


class TimezoneStore:
    """Stores a single timezone string supplied by the client UI."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._cached: Optional[str] = None
        self._load()

    def _load(self) -> None:
        try:
            value = self._path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            self._cached = None
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("failed to read timezone file", extra={"error": str(exc)})
            self._cached = None
            return

        self._cached = value or None

    def get_timezone(self, default: str = "UTC") -> str:
        with self._lock:
            return self._cached or default

    def set_timezone(self, timezone_name: str) -> None:
        validated = self._validate(timezone_name)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(validated, encoding="utf-8")
            self._cached = validated
            logger.info("updated timezone preference", extra={"timezone": validated})

    def clear(self) -> None:
        with self._lock:
            self._cached = None
            try:
                if self._path.exists():
                    self._path.unlink()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("failed to clear timezone file", extra={"error": str(exc)})

    def _validate(self, timezone_name: str) -> str:
        candidate = (timezone_name or "").strip()
        if not candidate:
            raise ValueError("timezone must be a non-empty string")
        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {candidate}") from exc
        return candidate


_DATA_DIR = get_data_dir()
_TIMEZONE_PATH = _DATA_DIR / "timezone.txt"

_timezone_store = TimezoneStore(_TIMEZONE_PATH)


def get_timezone_store() -> TimezoneStore:
    return _timezone_store


__all__ = ["TimezoneStore", "get_timezone_store"]
