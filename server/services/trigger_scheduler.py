"""Background scheduler that watches trigger definitions and executes them."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Set

from ..agents.execution_agent.batch_manager import ExecutionBatchManager
from ..logging_config import logger
from ..utils.exceptions import (
    AgentExecutionError,
    OpenPokeError,
    ToolExecutionError,
    TriggerSchedulingError,
)
from .triggers import TriggerRecord, get_trigger_service
from .triggers.utils import parse_iso, to_storage_timestamp


UTC = timezone.utc


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class TriggerScheduler:
    """Polls stored triggers and launches execution agents when due.

    Thread-safety: This class is async-safe with proper lock coordination:
    - _lock protects start/stop operations and _running flag
    - _in_flight_lock protects the _in_flight set from concurrent access
    - All _in_flight access must be guarded by _in_flight_lock
    """

    def __init__(self, poll_interval_seconds: float = 10.0) -> None:
        self._poll_interval = poll_interval_seconds
        self._service = get_trigger_service()
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._in_flight: Set[int] = set()
        # Separate locks for different concerns to avoid deadlocks
        self._lock = asyncio.Lock()  # Protects start/stop operations
        self._in_flight_lock = asyncio.Lock()  # Protects _in_flight set

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
        logger.debug("Trigger scheduler loop starting")
        try:
            while self._running:
                logger.debug("Trigger scheduler polling cycle")
                await self._poll_once()
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise
        except (TriggerSchedulingError, AgentExecutionError, ToolExecutionError, OpenPokeError) as exc:  # pragma: no cover - defensive
            logger.exception(
                "Trigger scheduler loop crashed",
                extra={"error": str(exc), "error_type": type(exc).__name__},
            )
            raise

    async def _poll_once(self) -> None:
        """Poll for due triggers and schedule execution.

        Thread-safety: Acquires _in_flight_lock when checking/modifying _in_flight set
        to prevent race conditions with concurrent trigger executions.
        """
        logger.debug("Starting trigger poll")
        now = _utc_now()
        # Look ahead by poll interval + buffer to account for scheduling delays
        look_ahead = now + timedelta(seconds=self._poll_interval + 5)
        due_triggers = self._service.get_due_triggers(before=look_ahead)

        # Debug: Log the before timestamp
        before_iso = to_storage_timestamp(look_ahead)
        logger.debug("Looking for triggers due before", extra={"before": before_iso})

        if not due_triggers:
            return

        for trigger in due_triggers:
            # Check if already in flight (with lock protection)
            async with self._in_flight_lock:
                if trigger.id in self._in_flight:
                    logger.debug(
                        "Trigger already in flight",
                        extra={"trigger_id": trigger.id, "agent": trigger.agent_name}
                    )
                    continue

                # Only execute if actually due (within poll interval of now)
                next_fire = parse_iso(trigger.next_trigger) if trigger.next_trigger else None
                if next_fire and (next_fire - now) > timedelta(seconds=self._poll_interval):
                    logger.debug(
                        "Trigger not yet due",
                        extra={
                            "trigger_id": trigger.id,
                            "next_fire": trigger.next_trigger,
                            "seconds_until_due": (next_fire - now).total_seconds()
                        }
                    )
                    continue

                # Mark as in-flight before spawning task to prevent duplicate execution
                self._in_flight.add(trigger.id)

            # Spawn task outside the lock to avoid blocking other operations
            asyncio.create_task(self._execute_trigger(trigger), name=f"trigger-{trigger.id}")

    async def _execute_trigger(self, trigger: TriggerRecord) -> None:
        """Execute a single trigger and handle success/failure.

        Thread-safety: Acquires _in_flight_lock in finally block to safely
        remove trigger from in-flight set, preventing race with _poll_once.
        """
        try:
            fired_at = _utc_now()
            start_time = _utc_now()
            instructions = self._format_instructions(trigger, fired_at)

            logger.info(
                "Dispatching trigger",
                extra={
                    "trigger_id": trigger.id,
                    "agent": trigger.agent_name,
                    "scheduled_for": trigger.next_trigger,
                    "fired_at": _isoformat(fired_at),
                    "payload_preview": trigger.payload[:100] + "..." if len(trigger.payload) > 100 else trigger.payload
                },
            )

            execution_manager = ExecutionBatchManager()
            result = await execution_manager.execute_agent(
                trigger.agent_name,
                instructions,
            )

            if result.success:
                execution_time = (_utc_now() - start_time).total_seconds()
                logger.info(
                    "Trigger completed successfully",
                    extra={
                        "trigger_id": trigger.id,
                        "agent": trigger.agent_name,
                        "response_length": len(result.response) if result.response else 0,
                        "execution_time_seconds": round(execution_time, 2)
                    }
                )
                self._handle_success(trigger, fired_at)
            else:
                error_text = result.error or result.response or "Unknown error"
                logger.warning(
                    "Trigger execution failed",
                    extra={
                        "trigger_id": trigger.id,
                        "agent": trigger.agent_name,
                        "error": error_text[:200] + "..." if len(error_text) > 200 else error_text
                    },
                )
                self._handle_failure(trigger, fired_at, error_text)
        except TriggerSchedulingError as exc:
            logger.error(
                "Trigger execution failed",
                extra={
                    "trigger_id": trigger.id,
                    "agent": trigger.agent_name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            self._handle_failure(trigger, _utc_now(), str(exc))
        except (AgentExecutionError, ToolExecutionError, OpenPokeError) as exc:
            logger.error(
                "Trigger execution failed",
                extra={
                    "trigger_id": trigger.id,
                    "agent": trigger.agent_name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            self._handle_failure(trigger, _utc_now(), str(exc))
        finally:
            # Remove from in-flight set with lock protection
            async with self._in_flight_lock:
                self._in_flight.discard(trigger.id)

    def _handle_success(self, trigger: TriggerRecord, fired_at: datetime) -> None:
        logger.debug(
            "Scheduling next occurrence for trigger",
            extra={"trigger_id": trigger.id, "agent": trigger.agent_name},
        )
        self._service.schedule_next_occurrence(trigger, fired_at=fired_at)

    def _handle_failure(self, trigger: TriggerRecord, fired_at: datetime, error: str) -> None:
        logger.warning(
            "Trigger execution failed",
            extra={
                "trigger_id": trigger.id,
                "agent": trigger.agent_name,
                "error": error,
            },
        )
        self._service.record_failure(trigger, error)
        if trigger.recurrence_rule:
            self._service.schedule_next_occurrence(trigger, fired_at=fired_at)
        else:
            self._service.clear_next_fire(trigger.id, agent_name=trigger.agent_name)

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
