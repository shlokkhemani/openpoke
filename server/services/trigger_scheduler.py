"""Background scheduler that watches trigger definitions and executes them."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional, Set

from ..agents.execution_agent.batch_manager import ExecutionBatchManager
from ..agents.execution_agent.runtime import ExecutionResult
from ..logging_config import logger
from .agents.store import get_agent_store
from .triggers import TriggerRecord, get_trigger_service


UTC = timezone.utc
UNKNOWN_AGENT_MARKER = "unknown agent id"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class TriggerScheduler:
    """Polls stored triggers and launches execution agents when due."""

    def __init__(self, poll_interval_seconds: float = 10.0) -> None:
        self._poll_interval = poll_interval_seconds
        self._service = get_trigger_service()
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._in_flight: Set[int] = set()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                return
            loop = asyncio.get_running_loop()
            self._running = True
            self._task = loop.create_task(self._run(), name="trigger-scheduler")
            logger.info("Trigger scheduler started", extra={"interval": self._poll_interval})

    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                self._task = None
                logger.info("Trigger scheduler stopped")

    async def _run(self) -> None:
        try:
            while self._running:
                await self._poll_once()
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Trigger scheduler loop crashed", extra={"error": str(exc)})

    async def _poll_once(self) -> None:
        now = _utc_now()
        due_triggers = self._service.get_due_triggers(before=now)
        if not due_triggers:
            return

        for trigger in due_triggers:
            if trigger.id in self._in_flight:
                continue
            self._in_flight.add(trigger.id)
            asyncio.create_task(self._execute_trigger(trigger), name=f"trigger-{trigger.id}")

    async def _execute_trigger(self, trigger: TriggerRecord) -> None:
        try:
            agents = get_agent_store()
            if agents.get(trigger.agent_id) is None:
                # Pre-id rows hold agent names; never fire, create or record a use for them.
                # The marker is written once so polling does not re-log or rewrite the row forever.
                if trigger.last_error == UNKNOWN_AGENT_MARKER:
                    logger.debug(
                        "Trigger skipped: unknown agent id (already marked)",
                        extra={"trigger_id": trigger.id, "agent": trigger.agent_id},
                    )
                    return
                logger.warning(
                    "Trigger skipped: unknown agent id",
                    extra={"trigger_id": trigger.id, "agent": trigger.agent_id},
                )
                self._service.record_failure(trigger, UNKNOWN_AGENT_MARKER)
                return
            fired_at = _utc_now()
            instructions = self._format_instructions(trigger, fired_at)
            logger.info(
                "Dispatching trigger",
                extra={
                    "trigger_id": trigger.id,
                    "agent": trigger.agent_id,
                    "scheduled_for": trigger.next_trigger,
                },
            )
            execution_manager = ExecutionBatchManager()
            result = await execution_manager.execute_agent(
                trigger.agent_id,
                instructions,
            )
            if result.success:
                self._handle_success(trigger, fired_at)
            else:
                error_text = result.error or result.response
                self._handle_failure(trigger, fired_at, error_text)
        except Exception as exc:  # pragma: no cover - defensive
            self._handle_failure(trigger, _utc_now(), str(exc))
            logger.exception(
                "Trigger execution failed unexpectedly",
                extra={"trigger_id": trigger.id, "agent": trigger.agent_id},
            )
        finally:
            self._in_flight.discard(trigger.id)

    def _handle_success(self, trigger: TriggerRecord, fired_at: datetime) -> None:
        logger.info(
            "Trigger completed",
            extra={"trigger_id": trigger.id, "agent": trigger.agent_id},
        )
        try:
            get_agent_store().record_use(trigger.agent_id, "trigger", fired_at)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("recording trigger use failed", extra={"error": str(exc)})
        self._service.schedule_next_occurrence(trigger, fired_at=fired_at)

    def _handle_failure(self, trigger: TriggerRecord, fired_at: datetime, error: str) -> None:
        logger.warning(
            "Trigger execution failed",
            extra={
                "trigger_id": trigger.id,
                "agent": trigger.agent_id,
                "error": error,
            },
        )
        self._service.record_failure(trigger, error)
        if trigger.recurrence_rule:
            self._service.schedule_next_occurrence(trigger, fired_at=fired_at)
        else:
            self._service.clear_next_fire(trigger.id, agent_id=trigger.agent_id)

    def _format_instructions(self, trigger: TriggerRecord, fired_at: datetime) -> str:
        scheduled_for = trigger.next_trigger or _isoformat(fired_at)
        metadata_lines = [f"Trigger ID: {trigger.id}"]
        if trigger.recurrence_rule:
            metadata_lines.append(f"Recurrence: {trigger.recurrence_rule}")
        if trigger.timezone:
            metadata_lines.append(f"Timezone: {trigger.timezone}")
        if trigger.start_time:
            metadata_lines.append(f"Start Time (UTC): {trigger.start_time}")

        metadata = "\n".join(f"- {line}" for line in metadata_lines)
        return (
            f"Trigger fired at {_isoformat(fired_at)} (UTC).\n"
            f"Scheduled occurrence time: {scheduled_for}.\n\n"
            f"Metadata:\n{metadata}\n\n"
            f"Payload:\n{trigger.payload}"
        )


_scheduler_instance: Optional[TriggerScheduler] = None


def get_trigger_scheduler() -> TriggerScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TriggerScheduler()
    return _scheduler_instance


__all__ = ["TriggerScheduler", "get_trigger_scheduler"]
