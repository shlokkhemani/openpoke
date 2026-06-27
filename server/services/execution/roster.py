"""Agent roster management with lifecycle status tracking."""

import json
import fcntl
import time
from pathlib import Path
from typing import Dict, List

from ...logging_config import logger


class AgentRoster:
    """Roster that tracks agent names and their lifecycle status.

    Storage format (roster.json):
        {"agents": {"name": "active"|"completed", ...}}

    Backward compat: if a plain list is found on load, all entries
    are treated as "active".
    """

    MAX_COMPLETED = 20  # Keep at most this many completed agents

    def __init__(self, roster_path: Path):
        self._roster_path = roster_path
        self._agents: Dict[str, str] = {}  # name -> status
        self.load()

    def load(self) -> None:
        """Load agent roster from roster.json."""
        if self._roster_path.exists():
            try:
                with open(self._roster_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "agents" in data:
                        self._agents = {
                            str(k): str(v) for k, v in data["agents"].items()
                        }
                    elif isinstance(data, list):
                        # Backward compat: plain list → all active
                        self._agents = {str(name): "active" for name in data}
                        self.save()
                    else:
                        self._agents = {}
            except Exception as exc:
                logger.warning(f"Failed to load roster.json: {exc}")
                self._agents = {}
        else:
            self._agents = {}
            self.save()

    def save(self) -> None:
        """Save agent roster to roster.json with file locking."""
        max_retries = 5
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                self._roster_path.parent.mkdir(parents=True, exist_ok=True)

                with open(self._roster_path, 'w') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    try:
                        json.dump({"agents": self._agents}, f, indent=2)
                        return
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            except BlockingIOError:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.warning("Failed to acquire lock on roster.json after retries")
            except Exception as exc:
                logger.warning(f"Failed to save roster.json: {exc}")
                break

    def add_agent(self, agent_name: str) -> None:
        """Add an agent as active if not already present."""
        if agent_name not in self._agents:
            self._agents[agent_name] = "active"
            self.save()

    def complete_agent(self, agent_name: str) -> None:
        """Mark an agent as completed and prune oldest completed if over cap."""
        if agent_name in self._agents:
            self._agents[agent_name] = "completed"
            self._prune_completed()
            self.save()
            logger.info(f"Agent marked completed: {agent_name}")

    def _prune_completed(self) -> None:
        """Remove oldest completed agents if over MAX_COMPLETED."""
        completed = [n for n, s in self._agents.items() if s == "completed"]
        excess = len(completed) - self.MAX_COMPLETED
        if excess > 0:
            for name in completed[:excess]:
                del self._agents[name]

    def get_agents(self) -> list[str]:
        """Get list of all agent names (all statuses)."""
        return list(self._agents.keys())

    def get_active_agents(self) -> list[str]:
        """Get list of currently active agent names."""
        return [name for name, status in self._agents.items() if status == "active"]

    def get_completed_agents(self) -> list[str]:
        """Get list of completed agent names."""
        return [name for name, status in self._agents.items() if status == "completed"]

    def get_agent_status(self, agent_name: str) -> str | None:
        """Get the status of a specific agent, or None if not found."""
        return self._agents.get(agent_name)

    def clear(self) -> None:
        """Clear the agent roster."""
        self._agents = {}
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
