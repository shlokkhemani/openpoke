"""Pure organization logic for reminders.

Kept free of I/O so the sorting and grouping rules can be unit tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
from typing import List, Optional, Sequence

from ..triggers import TriggerRecord
from ..triggers.utils import parse_iso


@dataclass(frozen=True)
class ReminderItem:
    """One reminder, resolved against a reference time."""

    id: int
    summary: str
    when: Optional[datetime]
    when_label: str
    recurrence_rule: Optional[str] = None
    overdue: bool = False


@dataclass
class ReminderGroup:
    """A homogeneous slice of the reminder list."""

    items: List[ReminderItem] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)


@dataclass
class ReminderDigest:
    """All reminders, organized for decision making."""

    overdue: ReminderGroup = field(default_factory=ReminderGroup)
    due: ReminderGroup = field(default_factory=ReminderGroup)
    imminent: ReminderGroup = field(default_factory=ReminderGroup)
    upcoming: List[ReminderItem] = field(default_factory=list)
    total_active: int = 0

    @property
    def needs_attention(self) -> bool:
        """True when something has fired or is about to."""
        return bool(self.overdue or self.due)

    def due_items(self) -> List[ReminderItem]:
        """Items that fired and still deserve a notification."""
        return [*self.overdue.items, *self.due.items]


_SUMMARY_LIMIT = 90


def _escape(value: str) -> str:
    """Escape tag-breaking characters so a payload cannot forge prompt structure.

    Reminder payloads originate from user text and from model output, so they
    must be treated as untrusted. Without this a payload containing
    ``</reminders>`` could close the block and inject a fake turn.
    """
    return escape(value, quote=False)


def _summarize(payload: str) -> str:
    """Collapse a reminder payload into one short, tag-safe line."""
    collapsed = " ".join((payload or "").split())
    if len(collapsed) <= _SUMMARY_LIMIT:
        return _escape(collapsed)
    return escape(collapsed[: _SUMMARY_LIMIT - 1].rstrip()) + "…"


# Public alias so every render path shares one escaping rule.
summarize_payload = _summarize


def _when_label(when: Optional[datetime], now: datetime) -> str:
    """Human-friendly relative label used in the prompt block."""
    if when is None:
        return "no schedule"

    delta = when - now
    seconds = delta.total_seconds()

    if seconds < 0:
        overdue_for = -seconds
        if overdue_for < 3600:
            return f"{-int(overdue_for // 60)}m overdue"
        if overdue_for < 86400:
            return f"{-int(overdue_for // 3600)}h overdue"
        return f"{-int(overdue_for // 86400)}d overdue"

    if seconds < 90:
        return "due now"
    if seconds < 3600:
        return f"in {int(seconds // 60)}m"
    if seconds < 86400:
        return f"in {int(seconds // 3600)}h"
    return f"in {int(seconds // 86400)}d"


def build_digest(
    records: Sequence[TriggerRecord],
    *,
    now: datetime,
    imminent_window: timedelta,
) -> ReminderDigest:
    """Group reminders into overdue / due / imminent / upcoming.

    Only active reminders are considered; paused and completed ones are ignored
    because they will not fire.
    """

    digest = ReminderDigest()
    active: List[ReminderItem] = []

    for record in records:
        if (record.status or "").strip().lower() != "active":
            continue

        when = parse_iso(record.next_trigger) if record.next_trigger else None
        item = ReminderItem(
            id=record.id,
            summary=_summarize(record.payload),
            when=when,
            when_label=_when_label(when, now),
            recurrence_rule=record.recurrence_rule,
            overdue=bool(when and when < now - imminent_window),
        )
        active.append(item)

    # Sort by fire time; undated reminders sink to the end.
    active.sort(key=lambda item: (item.when is None, item.when or now))

    for item in active:
        if item.when is None:
            digest.upcoming.append(item)
        elif item.when <= now:
            if item.overdue:
                digest.overdue.items.append(item)
            else:
                digest.due.items.append(item)
        elif item.when <= now + imminent_window:
            digest.imminent.items.append(item)
        else:
            digest.upcoming.append(item)

    digest.total_active = len(active)
    return digest


__all__ = [
    "ReminderDigest",
    "ReminderGroup",
    "ReminderItem",
    "build_digest",
]
