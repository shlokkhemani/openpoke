"""Agent roster: one record per execution agent (name, summary, status, entities, activity)."""

from __future__ import annotations

import fcntl
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...logging_config import logger

VALID_STATUSES = ("active", "waiting_on_user", "waiting_on_external", "done")
OPEN_STATUSES = ("active", "waiting_on_user", "waiting_on_external")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AgentRecord:
    """Roster entry describing one execution agent."""

    name: str
    summary: str = ""
    status: str = "active"
    entities: List[str] = field(default_factory=list)
    last_active: str = field(default_factory=_now_iso)
    archived: bool = False

    @property
    def is_closed(self) -> bool:
        return self.archived or self.status == "done"

    @classmethod
    def from_raw(cls, raw: Any) -> Optional["AgentRecord"]:
        """Accept both the legacy format (plain name) and the record format."""
        if isinstance(raw, str):
            return cls(name=raw) if raw.strip() else None
        if isinstance(raw, dict) and isinstance(raw.get("name"), str) and raw["name"].strip():
            status = raw.get("status") if raw.get("status") in VALID_STATUSES else "active"
            entities = raw.get("entities") if isinstance(raw.get("entities"), list) else []
            return cls(
                name=raw["name"],
                summary=str(raw.get("summary") or ""),
                status=status,
                entities=[str(item) for item in entities],
                last_active=str(raw.get("last_active") or _now_iso()),
                archived=bool(raw.get("archived", False)),
            )
        return None


class AgentRoster:
    """Roster persisted in roster.json as a list of agent records."""

    def __init__(self, roster_path: Path):
        self._roster_path = roster_path
        self._records: Dict[str, AgentRecord] = {}
        self._lock = threading.Lock()
        self.load()

    # ------------------------------------------------------------------ persistence
    def load(self) -> None:
        """Load records from roster.json (legacy list-of-names files are upgraded in memory)."""
        records: Dict[str, AgentRecord] = {}
        if self._roster_path.exists():
            try:
                data = json.loads(self._roster_path.read_text(encoding="utf-8") or "[]")
                if isinstance(data, list):
                    for raw in data:
                        record = AgentRecord.from_raw(raw)
                        if record is not None:
                            records[record.name] = record
            except Exception as exc:
                logger.warning(f"Failed to load roster.json: {exc}")
        with self._lock:
            self._records = records
        if not self._roster_path.exists():
            self.save()

    def save(self) -> None:
        """Save records to roster.json with file locking."""
        with self._lock:
            payload = [asdict(record) for record in self._records.values()]

        max_retries = 5
        retry_delay = 0.1
        for attempt in range(max_retries):
            try:
                self._roster_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._roster_path, "w") as handle:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    try:
                        json.dump(payload, handle, indent=2)
                        return
                    finally:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except BlockingIOError:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.warning("Failed to acquire lock on roster.json after retries")
            except Exception as exc:
                logger.warning(f"Failed to save roster.json: {exc}")
                break

    # ------------------------------------------------------------------ reads
    def get_agents(self) -> List[str]:
        """Return all agent names (kept for backward compatibility)."""
        with self._lock:
            return list(self._records.keys())

    def records(self) -> List[AgentRecord]:
        with self._lock:
            return list(self._records.values())

    def get_record(self, agent_name: str) -> Optional[AgentRecord]:
        with self._lock:
            return self._records.get(agent_name)

    # ------------------------------------------------------------------ writes
    def add_agent(self, agent_name: str) -> None:
        """Add an agent to the roster if not already present."""
        with self._lock:
            if agent_name in self._records:
                return
            self._records[agent_name] = AgentRecord(name=agent_name)
        self.save()

    def update_record(
        self,
        agent_name: str,
        *,
        summary: Optional[str] = None,
        status: Optional[str] = None,
        entities: Optional[List[str]] = None,
        archived: Optional[bool] = None,
    ) -> AgentRecord:
        """Update fields on an agent record, creating it if missing."""
        if status is not None and status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {', '.join(VALID_STATUSES)}")
        with self._lock:
            record = self._records.get(agent_name) or AgentRecord(name=agent_name)
            if summary is not None:
                record.summary = summary.strip()
            if status is not None:
                record.status = status
            if entities is not None:
                merged = list(dict.fromkeys([*record.entities, *[str(e).strip() for e in entities if str(e).strip()]]))
                record.entities = merged[-30:]
            if archived is not None:
                record.archived = archived
            record.last_active = _now_iso()
            self._records[agent_name] = record
        self.save()
        return record

    def touch(self, agent_name: str) -> None:
        """Mark an agent as recently active."""
        with self._lock:
            record = self._records.get(agent_name)
            if record is None:
                record = AgentRecord(name=agent_name)
                self._records[agent_name] = record
            record.last_active = _now_iso()
        self.save()

    def clear(self) -> None:
        """Clear the agent roster."""
        with self._lock:
            self._records = {}
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
