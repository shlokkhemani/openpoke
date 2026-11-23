"""Execution agent roster with focused selection for the interaction agent."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...logging_config import logger

# Agents idle for longer than this are archived and kept out of the prompt.
ARCHIVE_AFTER_DAYS = 7
# Upper bound on how many agents reach the interaction agent each turn.
MAX_PROMPT_AGENTS = 15
# Characters kept from the last instruction, used as a relevance hint.
INSTRUCTION_SNIPPET_LENGTH = 80

_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "for",
        "from",
        "get",
        "has",
        "have",
        "her",
        "him",
        "his",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "please",
        "send",
        "she",
        "so",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "up",
        "us",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    }
)


def _lock_file(file_obj) -> None:
    """Acquire a non-blocking exclusive lock. Raises BlockingIOError if held."""
    if os.name == "nt":
        import msvcrt

        file_obj.seek(0)
        if not file_obj.read(1):
            file_obj.write(b"\0")
            file_obj.flush()
        file_obj.seek(0)
        try:
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError(str(exc)) from exc
        return

    import fcntl

    fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(file_obj) -> None:
    if os.name == "nt":
        import msvcrt

        file_obj.seek(0)
        try:
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return

    import fcntl

    fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(moment: Optional[datetime]) -> Optional[str]:
    if moment is None:
        return None
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _from_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _tokens(text: str) -> set[str]:
    """Split text into lowercase words, dropping short filler words."""
    if not text:
        return set()
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {word for word in cleaned.split() if len(word) > 2 and word not in _STOPWORDS}


def _snippet(instructions: Optional[str]) -> str:
    """Collapse an instruction into a single short line."""
    if not instructions:
        return ""
    collapsed = " ".join(str(instructions).split())
    if len(collapsed) <= INSTRUCTION_SNIPPET_LENGTH:
        return collapsed
    return collapsed[: INSTRUCTION_SNIPPET_LENGTH - 1].rstrip() + "…"


def _is_reserved_identity(agent_name: Optional[str]) -> bool:
    """True for identities that must never occupy a prompt slot.

    Imported lazily to avoid a circular import: the reminders package depends on
    the trigger tools, which live under the execution agent.
    """
    from ..reminders import is_reminder_agent

    return is_reminder_agent(agent_name)


@dataclass
class AgentRecord:
    """One execution agent and the activity metadata used to rank it."""

    name: str
    created_at: Optional[str] = None
    last_active_at: Optional[str] = None
    last_instructions: str = ""
    use_count: int = 0
    archived: bool = False

    @property
    def activity_at(self) -> Optional[datetime]:
        """Most recent activity, falling back to creation time."""
        return _from_iso(self.last_active_at) or _from_iso(self.created_at)

    def is_dormant(self, *, now: Optional[datetime] = None, days: int = ARCHIVE_AFTER_DAYS) -> bool:
        reference = self.activity_at
        if reference is None:
            return False
        cutoff = (now or _utc_now()) - timedelta(days=days)
        return reference < cutoff

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "last_instructions": self.last_instructions,
            "use_count": self.use_count,
            "archived": self.archived,
        }

    @classmethod
    def from_entry(cls, entry: Any) -> Optional["AgentRecord"]:
        """Build a record from a legacy name string or a stored dict."""
        if isinstance(entry, str):
            name = entry.strip()
            if not name:
                return None
            return cls(name=name, created_at=_to_iso(_utc_now()))
        if not isinstance(entry, dict):
            return None
        name = str(entry.get("name") or "").strip()
        if not name:
            return None
        try:
            use_count = int(entry.get("use_count") or 0)
        except (TypeError, ValueError):
            use_count = 0
        return cls(
            name=name,
            created_at=entry.get("created_at") or None,
            last_active_at=entry.get("last_active_at") or None,
            last_instructions=str(entry.get("last_instructions") or ""),
            use_count=max(use_count, 0),
            archived=bool(entry.get("archived")),
        )


class AgentRoster:
    """Execution agent roster persisted as JSON, rendered as a focused subset."""

    def __init__(self, roster_path: Path):
        self._roster_path = roster_path
        self._records: List[AgentRecord] = []
        self.load()

    def load(self) -> None:
        """Load roster entries, migrating the legacy list of names."""
        migrated = False
        if self._roster_path.exists():
            try:
                with open(self._roster_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                entries = data if isinstance(data, list) else []
                records: List[AgentRecord] = []
                seen: set[str] = set()
                for entry in entries:
                    record = AgentRecord.from_entry(entry)
                    if record is None or record.name in seen:
                        continue
                    if not isinstance(entry, dict):
                        migrated = True
                    seen.add(record.name)
                    records.append(record)
                self._records = records
            except Exception as exc:
                logger.warning(f"Failed to load roster.json: {exc}")
                self._records = []
        else:
            self._records = []
            self.save()

        # Persist the migrated shape and any archive transitions from this load
        if self._refresh_archive_flags() or migrated:
            self.save()

    def save(self) -> None:
        """Save roster records to roster.json with file locking."""
        max_retries = 5
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                self._roster_path.parent.mkdir(parents=True, exist_ok=True)

                lock_path = self._roster_path.with_suffix(".lock")
                with open(lock_path, "a+b") as lockf:
                    _lock_file(lockf)
                    try:
                        with open(self._roster_path, "w", encoding="utf-8") as f:
                            json.dump([record.to_dict() for record in self._records], f, indent=2)
                        return
                    finally:
                        _unlock_file(lockf)

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

    def _refresh_archive_flags(self) -> bool:
        """Archive dormant agents and revive recently used ones. Returns True on change."""
        now = _utc_now()
        changed = False
        for record in self._records:
            should_archive = record.is_dormant(now=now)
            if record.archived != should_archive:
                record.archived = should_archive
                changed = True
        return changed

    def _find(self, agent_name: str) -> Optional[AgentRecord]:
        for record in self._records:
            if record.name == agent_name:
                return record
        return None

    def touch(self, agent_name: str, instructions: Optional[str] = None) -> bool:
        """Record use of an agent. Returns True when the agent was newly created."""
        name = (agent_name or "").strip()
        if not name:
            return False

        now = _utc_now()
        record = self._find(name)
        is_new = record is None
        if record is None:
            record = AgentRecord(name=name, created_at=_to_iso(now))
            self._records.append(record)

        record.last_active_at = _to_iso(now)
        record.use_count += 1
        record.archived = False
        snippet = _snippet(instructions)
        if snippet:
            record.last_instructions = snippet

        self.save()
        return is_new

    def add_agent(self, agent_name: str) -> None:
        """Add an agent to the roster if not already present."""
        self.touch(agent_name)

    def get_agents(self) -> list[str]:
        """Get the names of agents that are not archived."""
        return [record.name for record in self._records if not record.archived]

    def get_all_names(self) -> list[str]:
        """Get every agent name, archived included."""
        return [record.name for record in self._records]

    def get_records(self, *, include_archived: bool = False) -> List[AgentRecord]:
        records = [record for record in self._records if include_archived or not record.archived]
        return sorted(records, key=lambda record: record.activity_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    def select_for_prompt(
        self,
        latest_text: str,
        transcript: str = "",
        *,
        limit: int = MAX_PROMPT_AGENTS,
    ) -> List[AgentRecord]:
        """Pick the agents worth showing for this turn, capped at *limit*.

        Reminders are excluded: they live under a single reserved identity that
        the prompt renders as a compact digest instead, so they cost no slots.
        """
        if limit <= 0:
            return []

        candidates = self.get_records(include_archived=True)
        if not candidates:
            return []

        # Reminders never compete for an agent slot (see services.reminders).
        candidates = [
            record for record in candidates if not _is_reserved_identity(record.name)
        ]
        if not candidates:
            return []

        selected: List[AgentRecord] = []
        chosen: set[str] = set()

        def add(record: AgentRecord) -> None:
            if len(selected) >= limit or record.name in chosen:
                return
            chosen.add(record.name)
            selected.append(record)

        # Recent transcript mentions keep follow-ups pointed at the agent already doing the work
        lowered_transcript = (transcript or "").lower()
        for record in candidates:
            if record.name.lower() in lowered_transcript:
                add(record)

        # Word overlap recalls dormant agents that still match this request
        if len(selected) < limit:
            query_tokens = _tokens(latest_text)
            if query_tokens:
                scored: List[tuple[int, bool, float, AgentRecord]] = []
                for record in candidates:
                    if record.name in chosen:
                        continue
                    overlap = len(query_tokens & _tokens(f"{record.name} {record.last_instructions}"))
                    if overlap:
                        activity = record.activity_at or datetime.min.replace(tzinfo=timezone.utc)
                        scored.append((overlap, not record.archived, activity.timestamp(), record))
                scored.sort(key=lambda item: (-item[0], not item[1], -item[2]))
                for _, _, _, record in scored:
                    add(record)

        # Remaining slots go to the most recently active agents
        for record in candidates:
            if not record.archived:
                add(record)

        return selected

    def clear(self) -> None:
        """Clear the agent roster."""
        self._records = []
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


__all__ = [
    "ARCHIVE_AFTER_DAYS",
    "MAX_PROMPT_AGENTS",
    "AgentRecord",
    "AgentRoster",
    "get_agent_roster",
]
