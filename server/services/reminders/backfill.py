"""One-time migration of legacy triggers into the reserved reminder owner.

Before the reminder pathway existed, every trigger was stored under the
execution agent that created it. Those rows are invisible to the new digest and
still fire through the old execution-agent path, so two reminder systems run at
once.

This backfill moves legacy reminder rows under the reserved owner id while
recording the original owner as ``created_by``, so visibility and provenance
survive. It is idempotent: rows already under the reserved owner are skipped.

Triggers that look like real agent work (their payload expects the agent to run
tools) are left alone, because they are not reminders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ...logging_config import logger
from ..triggers import get_trigger_service
from .service import REMINDER_OWNER_ID, is_reminder_owner

# Payloads containing these phrases suggest a task, not a simple reminder.
_TASK_HINTS = (
    "email",
    "reply",
    "forward",
    "draft",
    "summarize",
    "search",
    "check",
    "send",
)


@dataclass
class BackfillReport:
    """Outcome of a backfill run."""

    scanned: int = 0
    migrated: int = 0
    skipped_already_owned: int = 0
    skipped_task_like: int = 0
    migrated_ids: List[int] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"scanned={self.scanned} migrated={self.migrated} "
            f"already_owned={self.skipped_already_owned} "
            f"left_as_tasks={self.skipped_task_like}"
        )


def backfill_legacy_triggers(
    *,
    migrate_task_like: bool = False,
    dry_run: bool = False,
    service=None,
) -> BackfillReport:
    """Move legacy reminder triggers under the reserved owner id.

    Args:
        migrate_task_like: When true, migrate every legacy trigger regardless of
            payload. Default is false so agent work items keep their owner.
        dry_run: Compute the report without writing anything.
        service: Optional TriggerService override, for tests or alternate stores.
    """
    service = service or get_trigger_service()
    report = BackfillReport()

    for record in service.list_all_triggers():
        report.scanned += 1

        if is_reminder_owner(record.agent_name):
            report.skipped_already_owned += 1
            continue

        # A trigger with no created_by predates provenance tracking.
        creator = record.created_by or record.agent_name

        if not migrate_task_like and _looks_like_task(record.payload):
            report.skipped_task_like += 1
            logger.info(
                "backfill: leaving task-like trigger with its agent",
                extra={"trigger_id": record.id, "agent": record.agent_name},
            )
            continue

        if not dry_run:
            moved = service.assign_owner(
                record.id, owner_id=REMINDER_OWNER_ID, created_by=creator
            )
            if not moved:
                logger.warning(
                    "backfill: could not migrate trigger",
                    extra={"trigger_id": record.id},
                )
                continue

        report.migrated += 1
        report.migrated_ids.append(record.id)
        logger.info(
            "backfill: migrated trigger",
            extra={
                "trigger_id": record.id,
                "from": record.agent_name,
                "created_by": creator,
                "dry_run": dry_run,
            },
        )

    logger.info("backfill complete", extra={"report": report.summary()})
    return report


def _looks_like_task(payload: Optional[str]) -> bool:
    """Heuristic: does this payload ask an agent to do work rather than notify?"""
    text = (payload or "").lower()
    return any(hint in text for hint in _TASK_HINTS)


__all__ = ["BackfillReport", "backfill_legacy_triggers"]
