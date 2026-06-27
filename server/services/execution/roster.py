"""Agent roster management with lifecycle status + category tracking."""

import json
import fcntl
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...logging_config import logger


# Category inference rules: (keywords in agent name) → category
_CATEGORY_RULES: List[Tuple[List[str], str]] = [
    (["email", "mail", "send", "draft", "compose"], "communication"),
    (["research", "search", "find", "lookup", "investigate"], "research"),
    (["book", "booking", "reserve", "flight", "hotel", "travel"], "travel"),
    (["review", "code", "pr", "deploy", "refactor", "debug"], "engineering"),
    (["meeting", "schedule", "calendar", "appointment", "remind"], "scheduling"),
    (["analysis", "analyze", "report", "dashboard", "chart", "budget", "revenue", "financial"], "analysis"),
    (["write", "blog", "post", "article", "presentation", "slides", "document"], "content"),
    (["task", "todo", "process", "background", "job"], "task"),
]


def infer_category(agent_name: str) -> str:
    """Infer a category from the agent name using keyword rules."""
    name_lower = agent_name.lower()
    words = set(re.findall(r"[a-z]+", name_lower))

    best_category = "general"
    best_score = 0

    for keywords, category in _CATEGORY_RULES:
        score = sum(1 for kw in keywords if kw in words)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category


class AgentRoster:
    """Roster that tracks agent names, lifecycle status, and category.

    Storage format v3 (roster.json):
        {"agents": {"name": {"status": "active"|"completed", "category": "..."}}}

    Backward compat:
        v1 (plain list): all entries treated as active, category inferred
        v2 (name→status string): status preserved, category inferred
    """

    MAX_COMPLETED = 20  # Keep at most this many completed agents

    def __init__(self, roster_path: Path):
        self._roster_path = roster_path
        self._agents: Dict[str, Dict[str, str]] = {}  # name -> {status, category}
        self.load()

    def load(self) -> None:
        """Load agent roster from roster.json."""
        if self._roster_path.exists():
            try:
                with open(self._roster_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "agents" in data:
                        agents_raw = data["agents"]
                        if agents_raw and isinstance(next(iter(agents_raw.values())), dict):
                            # v3 format: {name: {status, category}}
                            self._agents = {
                                str(k): v for k, v in agents_raw.items()
                            }
                        else:
                            # v2 format: {name: status_string}
                            self._agents = {
                                str(k): {"status": str(v), "category": infer_category(str(k))}
                                for k, v in agents_raw.items()
                            }
                            self.save()  # migrate
                    elif isinstance(data, list):
                        # v1 format: plain list
                        self._agents = {
                            str(name): {"status": "active", "category": infer_category(str(name))}
                            for name in data
                        }
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
        """Add an agent as active with auto-inferred category."""
        if agent_name not in self._agents:
            self._agents[agent_name] = {
                "status": "active",
                "category": infer_category(agent_name),
            }
            self.save()

    def reactivate_agent(self, agent_name: str) -> None:
        """Re-activate a completed agent, moving it to most-recent position."""
        old_data = self._agents.pop(agent_name, None)
        category = old_data["category"] if old_data else infer_category(agent_name)
        self._agents[agent_name] = {"status": "active", "category": category}
        self.save()

    def complete_agent(self, agent_name: str) -> None:
        """Mark an agent as completed and prune oldest completed if over cap."""
        if agent_name in self._agents:
            self._agents[agent_name]["status"] = "completed"
            self._prune_completed()
            self.save()
            logger.info(f"Agent marked completed: {agent_name}")

    def _prune_completed(self) -> None:
        """Remove oldest completed agents if over MAX_COMPLETED."""
        completed = [n for n, d in self._agents.items() if d["status"] == "completed"]
        excess = len(completed) - self.MAX_COMPLETED
        if excess > 0:
            for name in completed[:excess]:
                del self._agents[name]

    def get_agents(self) -> list[str]:
        """Get list of all agent names (all statuses)."""
        return list(self._agents.keys())

    def get_active_agents(self) -> list[str]:
        """Get list of currently active agent names."""
        return [name for name, d in self._agents.items() if d["status"] == "active"]

    def get_completed_agents(self) -> list[str]:
        """Get list of completed agent names."""
        return [name for name, d in self._agents.items() if d["status"] == "completed"]

    def get_agent_status(self, agent_name: str) -> Optional[str]:
        """Get the status of a specific agent, or None if not found."""
        entry = self._agents.get(agent_name)
        return entry["status"] if entry else None

    def get_agent_category(self, agent_name: str) -> Optional[str]:
        """Get the category of a specific agent."""
        entry = self._agents.get(agent_name)
        return entry["category"] if entry else None

    def get_agents_by_category(self, category: str) -> list[str]:
        """Get all active agents matching a category."""
        return [
            name for name, d in self._agents.items()
            if d["status"] == "active" and d.get("category") == category
        ]

    def get_category_counts(self) -> Dict[str, int]:
        """Get count of active agents per category."""
        counts: Dict[str, int] = {}
        for name, d in self._agents.items():
            if d["status"] == "active":
                cat = d.get("category", "general")
                counts[cat] = counts.get(cat, 0) + 1
        return counts

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
