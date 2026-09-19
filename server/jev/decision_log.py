"""Append-only record of every typed decision, with its probabilities.

This exists for one reason: **thresholds are re-tunable offline only if the
probabilities were stored.** TypeSafe's own guidance is that cut points depend
on your data and must be swept against it, and a sweep over a stored log costs
nothing, while a sweep that has to re-ask the model costs a run of the whole
mailbox. https://docs.typesafe.ai/confidence

The log is bounded, JSON-lines, and lives beside the other runtime state in
``server/data/`` (git-ignored). It records probabilities, the verdict and the
reason, plus enough identity to find the message again. **It does not record
email bodies or tool arguments** — the point is to re-threshold, not to build a
second copy of the mailbox.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Mapping, Optional

from ..config import get_settings
from ..logging_config import logger

DEFAULT_MAX_ENTRIES = 2000


class DecisionLog:
    """Bounded JSON-lines log of typed decisions."""

    def __init__(self, path: Path, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._path = path
        self._max_entries = max(1, max_entries)
        self._lock = threading.Lock()
        self._entries: Deque[str] = deque(maxlen=self._max_entries)
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    # Append one decision record
    def record(
        self,
        *,
        kind: str,
        verdict: str,
        reason: str,
        probabilities: Mapping[str, float],
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        message_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """Record one decision. Never raises."""

        settings = get_settings()
        if not settings.jev_decision_log_enabled:
            return

        entry: Dict[str, Any] = {
            "ts": time.time(),
            "kind": kind,
            "verdict": verdict,
            "reason": reason,
            "model": model or settings.jev_model,
            "probabilities": {k: round(float(v), 4) for k, v in probabilities.items()},
        }
        if message_id:
            entry["message_id"] = message_id
        if sender:
            entry["sender"] = sender
        if subject:
            # A subject line is identity, not content; clipped so a pathological
            # subject cannot bloat the log.
            entry["subject"] = subject[:160]
        if tool_name:
            entry["tool"] = tool_name

        try:
            line = json.dumps(entry, ensure_ascii=False)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            logger.debug("Skipping unserializable decision log entry")
            return

        with self._lock:
            self._entries.append(line)
            self._persist_locked()

    # Read the log back, newest last
    def entries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return parsed records, oldest first."""

        with self._lock:
            raw = list(self._entries)
        if limit is not None:
            raw = raw[-limit:]

        parsed: List[Dict[str, Any]] = []
        for line in raw:
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:  # pragma: no cover - defensive
                continue
        return parsed

    # Summary counters: the three integers that say whether a gate is working
    def counters(self, kind: Optional[str] = None) -> Dict[str, int]:
        """Return per-verdict counts, optionally for one decision kind."""

        counts: Dict[str, int] = {}
        for entry in self.entries():
            if kind is not None and entry.get("kind") != kind:
                continue
            verdict = str(entry.get("verdict") or "unknown")
            counts[verdict] = counts.get(verdict, 0) + 1
        return counts

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._persist_locked()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:  # pragma: no cover - defensive
            logger.warning("Could not read the decision log", extra={"error": str(exc)})
            return
        for line in lines:
            stripped = line.strip()
            if stripped:
                self._entries.append(stripped)

    def _persist_locked(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text("\n".join(self._entries) + "\n", encoding="utf-8")
        except OSError as exc:  # pragma: no cover - defensive
            logger.warning("Could not write the decision log", extra={"error": str(exc)})


_log: Optional[DecisionLog] = None
_log_lock = threading.Lock()


# Return the process-wide decision log
def get_decision_log() -> DecisionLog:
    """Return the shared log, creating it on first use."""

    global _log

    if _log is not None:
        return _log
    with _log_lock:
        if _log is None:
            settings = get_settings()
            _log = DecisionLog(
                Path(settings.jev_decision_log_path),
                max_entries=settings.jev_decision_log_max_entries,
            )
    return _log


# Replace the shared log, for tests
def set_decision_log(log: Optional[DecisionLog]) -> None:
    """Install a log instance directly. Intended for tests."""

    global _log
    _log = log


__all__ = ["DecisionLog", "DEFAULT_MAX_ENTRIES", "get_decision_log", "set_decision_log"]
