"""Agent lifecycle: archive finished or idle agents, revive them on demand (problems-and-solutions §3c)."""

from __future__ import annotations

import asyncio
import shutil
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ...logging_config import logger
from .log_store import get_execution_agent_logs
from .roster import get_agent_roster

DEFAULT_IDLE_DAYS = 7
SWEEP_INTERVAL_SECONDS = 24 * 60 * 60


def _has_active_triggers(agent_name: str) -> bool:
    from ..triggers import get_trigger_service

    try:
        return any(t.status == "active" for t in get_trigger_service().list_triggers(agent_name=agent_name))
    except Exception as exc:  # pragma: no cover - defensive: keep the agent if unsure
        logger.warning("trigger lookup failed during sweep", extra={"agent": agent_name, "error": str(exc)})
        return True


def _parse(ts: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def archive(agent_name: str) -> None:
    """Move an agent's log (and compaction summary) to the archive and flag the record."""
    logs = get_execution_agent_logs()
    for path in logs.agent_files(agent_name):
        target = logs.archive_dir / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
    get_agent_roster().update_record(agent_name, archived=True)
    logger.info("agent archived", extra={"agent": agent_name})


def revive(agent_name: str) -> bool:
    """Bring an archived agent back. Returns True if it was archived."""
    roster = get_agent_roster()
    record = roster.get_record(agent_name)
    if record is None or not record.archived:
        return False
    logs = get_execution_agent_logs()
    for path in logs.archived_files(agent_name):
        shutil.move(str(path), str(logs.base_dir / path.name))
    roster.update_record(agent_name, archived=False, status="active")
    logger.info("agent revived", extra={"agent": agent_name})
    return True


def sweep_agents(idle_days: int = DEFAULT_IDLE_DAYS, now: Optional[datetime] = None) -> List[str]:
    """Archive agents that are done or idle, skipping any that still own active triggers."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=idle_days)
    archived: List[str] = []
    for record in get_agent_roster().records():
        if record.archived:
            continue
        last_active = _parse(record.last_active)
        idle = last_active is not None and last_active < cutoff
        if not (record.status == "done" or idle):
            continue
        if _has_active_triggers(record.name):
            continue
        archive(record.name)
        archived.append(record.name)
    return archived


class AgentSweeper:
    """Background task that runs `sweep_agents` once a day."""

    def __init__(self, interval_seconds: float = SWEEP_INTERVAL_SECONDS) -> None:
        self._interval = interval_seconds
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.get_running_loop().create_task(self._run(), name="agent-sweeper")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                archived = sweep_agents()
                if archived:
                    logger.info("agent sweep archived agents", extra={"count": len(archived)})
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("agent sweep failed", extra={"error": str(exc)})


_sweeper: Optional[AgentSweeper] = None


def get_agent_sweeper() -> AgentSweeper:
    global _sweeper
    if _sweeper is None:
        _sweeper = AgentSweeper()
    return _sweeper


__all__ = ["archive", "revive", "sweep_agents", "get_agent_sweeper", "AgentSweeper"]
