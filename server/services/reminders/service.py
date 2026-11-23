"""Reminder pathway: a single reserved agent identity for all reminders.

Every reminder used to be created against whichever execution agent happened to
handle the request, so a dozen reminders became a dozen roster entries competing
for the interaction agent's limited prompt slots. Reminders now live under one
reserved identity and are surfaced as a compact digest instead.

The reserved identity is never selected as an execution agent, so creating a
reminder costs zero interaction-agent capacity no matter how many exist.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ...agents.execution_agent.tools.triggers import _create_trigger_tool
from ..triggers import TriggerRecord, get_trigger_service
from ..timezone_store import get_timezone_store
from .organizer import ReminderDigest, ReminderItem, build_digest

# The one roster identity all reminders are stored under.
REMINDER_AGENT_NAME = "Reminders"

# Reminders due within this window are surfaced as "imminent" so the
# interaction agent can warn the user rather than only reacting after the fact.
IMMINENT_WINDOW = timedelta(hours=1)

# How many upcoming reminders the prompt block mentions by name.
PROMPT_HINT_LIMIT = 5


def is_reminder_agent(agent_name: Optional[str]) -> bool:
    """Return True when the name is the reserved reminder identity."""
    return (agent_name or "").strip().casefold() == REMINDER_AGENT_NAME.casefold()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_reminder(
    *,
    payload: str,
    recurrence_rule: Optional[str] = None,
    start_time: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, object]:
    """Create a reminder under the reserved identity.

    Wraps the existing trigger tool so validation, timezone handling, and
    logging all keep working unchanged.
    """

    return _create_trigger_tool(
        agent_name=REMINDER_AGENT_NAME,
        payload=payload,
        recurrence_rule=recurrence_rule,
        start_time=start_time,
        status=status,
    )


class ReminderService:
    """Organizes, sorts, and digests the reminders held by the trigger store."""

    def __init__(self, now_provider=None) -> None:
        self._service = get_trigger_service()
        self._now = now_provider or _utc_now

    def create(
        self,
        *,
        payload: str,
        recurrence_rule: Optional[str] = None,
        start_time: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, object]:
        """Create a reminder owned by the reserved identity."""
        return create_reminder(
            payload=payload,
            recurrence_rule=recurrence_rule,
            start_time=start_time,
            status=status,
        )

    def list_reminders(self) -> List[TriggerRecord]:
        """Return every reminder, soonest first."""
        return self._service.list_triggers(agent_name=REMINDER_AGENT_NAME)

    def update(
        self,
        trigger_id: int,
        *,
        payload: Optional[str] = None,
        recurrence_rule: Optional[str] = None,
        start_time: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[TriggerRecord]:
        """Update a reminder by id."""
        return self._service.update_trigger(
            int(trigger_id),
            agent_name=REMINDER_AGENT_NAME,
            payload=payload,
            recurrence_rule=recurrence_rule,
            start_time=start_time,
            timezone_name=get_timezone_store().get_timezone(),
            status=status,
        )

    def digest(self) -> ReminderDigest:
        """Return reminders organized into due / imminent / scheduled groups."""
        now = self._now()
        return build_digest(
            self.list_reminders(),
            now=now,
            imminent_window=IMMINENT_WINDOW,
        )

    def render_prompt_block(self, *, hint_limit: int = PROMPT_HINT_LIMIT) -> str:
        """Render the compact reminder summary injected into the prompt.

        This replaces the old behaviour where each reminder consumed a full
        agent slot. An empty string means there is nothing worth mentioning.
        """
        digest = self.digest()
        if not digest.total_active:
            return ""

        lines: List[str] = [f"Active reminders: {digest.total_active}"]
        if digest.due:
            lines.append(f"- {len(digest.due)} due now")
        if digest.imminent:
            lines.append(f"- {len(digest.imminent)} due within the hour")
        if digest.overdue:
            lines.append(f"- {len(digest.overdue)} overdue")

        upcoming = digest.upcoming[:hint_limit]
        if upcoming:
            rendered = "; ".join(
                f"{item.summary} ({item.when_label})" for item in upcoming
            )
            lines.append(f"- Upcoming: {rendered}")
            remaining = digest.total_active - len(digest.overdue) - len(digest.due) - len(digest.imminent) - len(upcoming)
            if remaining > 0:
                lines.append(f"- ...and {remaining} more scheduled")

        return "\n".join(lines)

    def render_due_notification(self, fired: Optional[List[TriggerRecord]] = None) -> str:
        """Render the one notification sent when reminders fire.

        Replaces N per-trigger execution agents with a single interaction-agent
        message. Passing the triggers that just fired keeps the wording accurate
        even when other reminders are also due.
        """
        digest = self.digest()
        lines: List[str] = []

        just_fired = [
            ReminderItem(
                id=record.id,
                summary=" ".join((record.payload or "").split())[:90],
                when=None,
                when_label="just now",
                recurrence_rule=record.recurrence_rule,
            )
            for record in (fired or [])
        ]

        if just_fired:
            header = (
                "Reminder due:" if len(just_fired) == 1 else
                f"{len(just_fired)} reminders due:"
            )
            lines.append(header)
            for item in just_fired:
                marker = " (recurring)" if item.recurrence_rule else ""
                lines.append(f"- {item.summary}{marker}")

        # Surface anything else overdue so the user sees the full picture once
        already = {item.id for item in just_fired}
        extra_overdue = [i for i in digest.overdue.items if i.id not in already]
        if extra_overdue:
            lines.append(f"Also overdue ({len(extra_overdue)}):")
            for item in extra_overdue:
                lines.append(f"- {item.summary} ({item.when_label})")

        if not lines:
            return ""

        return "Reminder notification:\n" + "\n".join(lines)


_service_instance: Optional[ReminderService] = None


def get_reminder_service() -> ReminderService:
    """Return the shared reminder service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ReminderService()
    return _service_instance


__all__ = [
    "IMMINENT_WINDOW",
    "PROMPT_HINT_LIMIT",
    "REMINDER_AGENT_NAME",
    "ReminderService",
    "create_reminder",
    "get_reminder_service",
    "is_reminder_agent",
]
