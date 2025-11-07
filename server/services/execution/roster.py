"""Simple agent roster management - just a list of agent names."""

from __future__ import annotations

import json
import fcntl
import time
from pathlib import Path
from typing import Iterable, Tuple

from ...logging_config import logger


class AgentRoster:
    """Simple roster that stores agent names in a JSON file."""

    def __init__(self, roster_path: Path):
        self._roster_path = roster_path
        self._agents: list[str] = []
        self.load()

    @staticmethod
    def _clean_name(name: str) -> str:
        """Collapse whitespace and strip surrounding spaces from an agent name."""

        return " ".join(name.split())

    @staticmethod
    def _normalized_key(name: str) -> str:
        """Return the deduplication key for an agent name."""

        return AgentRoster._clean_name(name).lower()

    @classmethod
    def _sanitize(cls, names: Iterable[str]) -> Tuple[list[str], list[str]]:
        """Normalize names and drop duplicates while preserving order."""

        unique: list[str] = []
        removed: list[str] = []
        seen: set[str] = set()

        for raw in names:
            cleaned = cls._clean_name(str(raw))
            if not cleaned:
                removed.append(str(raw))
                continue

            key = cls._normalized_key(cleaned)
            if key in seen:
                removed.append(cleaned)
                continue

            seen.add(key)
            unique.append(cleaned)

        return unique, removed

    def load(self) -> None:
        """Load agent names from roster.json."""

        original: list[str] = []

        if self._roster_path.exists():
            try:
                with open(self._roster_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        original = [str(name) for name in data]
            except Exception as exc:
                logger.warning(f"Failed to load roster.json: {exc}")

        sanitized, removed = self._sanitize(original)
        self._agents = sanitized

        if not self._roster_path.exists() or sanitized != original:
            self.save()

        if removed:
            logger.info("Pruned duplicate or invalid agent entries", extra={"removed_agents": removed})

    def save(self) -> None:
        """Save agent names to roster.json with file locking."""

        max_retries = 5
        retry_delay = 0.1

        sanitized, _ = self._sanitize(self._agents)
        self._agents = sanitized

        for attempt in range(max_retries):
            try:
                self._roster_path.parent.mkdir(parents=True, exist_ok=True)

                # Open file and acquire exclusive lock
                with open(self._roster_path, 'w') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    try:
                        json.dump(self._agents, f, indent=2)
                        return
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            except BlockingIOError:
                # Lock is held by another process
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.warning("Failed to acquire lock on roster.json after retries")
            except Exception as exc:
                logger.warning(f"Failed to save roster.json: {exc}")
                break

    def prune_duplicates(self) -> list[str]:
        """Remove duplicate agent names from the roster, returning the discarded entries."""

        sanitized, removed = self._sanitize(self._agents)
        if sanitized != self._agents:
            self._agents = sanitized
            self.save()

        if removed:
            logger.info("Removed duplicate agents", extra={"removed_agents": removed})

        return removed

    def add_agent(self, agent_name: str) -> None:
        """Add an agent to the roster if not already present."""

        cleaned = self._clean_name(agent_name)
        if not cleaned:
            return

        key = self._normalized_key(cleaned)
        if key not in {self._normalized_key(name) for name in self._agents}:
            self._agents.append(cleaned)
            self.save()

    def has_agent(self, agent_name: str) -> bool:
        """Return True if an agent already exists in the roster (case-insensitive)."""

        key = self._normalized_key(agent_name)
        return any(self._normalized_key(existing) == key for existing in self._agents)

    def get_agents(self) -> list[str]:
        """Get list of all agent names."""

        return list(self._agents)

    def remove_agent(self, agent_name: str) -> bool:
        """Remove an agent from the roster using case-insensitive matching."""

        cleaned = self._clean_name(agent_name)
        if not cleaned:
            return False

        target = self._normalized_key(cleaned)
        remaining = [name for name in self._agents if self._normalized_key(name) != target]

        if len(remaining) == len(self._agents):
            return False

        self._agents = remaining
        self.save()
        logger.info("Removed agent from roster", extra={"removed_agent": cleaned})
        return True

    def clear(self) -> None:
        """Clear the agent roster."""

        self._agents = []
        try:
            if self._roster_path.exists():
                self._roster_path.unlink()
            logger.info("Cleared agent roster")
        except Exception as exc:
            logger.warning(f"Failed to clear roster.json: {exc}")


_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_ROSTER_PATH = _DATA_DIR / "execution_agents" / "roster.json"

_agent_roster = AgentRoster(_ROSTER_PATH)


def get_agent_roster() -> AgentRoster:
    """Get the singleton roster instance."""
    return _agent_roster
