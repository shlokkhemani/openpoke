from __future__ import annotations

import re
from typing import List, Optional

from ..triggers.models import TriggerRecord
from .store import AgentRecord, ContactRecord

_DAYS = {
    "MO": "Monday", "TU": "Tuesday", "WE": "Wednesday", "TH": "Thursday",
    "FR": "Friday", "SA": "Saturday", "SU": "Sunday",
}
_UNSUPPORTED_PARTS = {"BYSETPOS", "BYMONTH", "BYMONTHDAY"}


def _format_time(hour: int, minute: int) -> str:
    suffix = "am" if hour < 12 else "pm"
    h = hour % 12 or 12
    return f"{h}{suffix}" if minute == 0 else f"{h}:{minute:02d}{suffix}"


def _time_of_day(parts: dict, rrule: str, start_time: Optional[str]) -> Optional[str]:
    if "BYHOUR" in parts:
        try:
            hour = int(parts["BYHOUR"].split(",")[0])
            minute = int(parts.get("BYMINUTE", "0").split(",")[0])
            return _format_time(hour, minute)
        except ValueError:
            return None
    m = re.search(r"DTSTART[^:\n]*:\d{8}T(\d{2})(\d{2})", rrule)
    if m:  # wall-clock time in the rule's own TZID: deliberately not converted
        return _format_time(int(m.group(1)), int(m.group(2)))
    if start_time:
        # start_time is UTC, so this can be off by the user's UTC offset.
        m = re.search(r"T(\d{2}):(\d{2})", start_time)
        if m:
            return _format_time(int(m.group(1)), int(m.group(2)))
    return None


def describe_schedule(rrule: str, start_time: Optional[str]) -> str:
    """Plain-English schedule for simple daily/weekly rules; anything else unchanged."""
    rule_line = next(
        (ln.strip()[len("RRULE:"):] for ln in rrule.splitlines() if ln.strip().startswith("RRULE:")),
        rrule.strip(),
    )
    parts = {}
    for piece in rule_line.split(";"):
        if "=" in piece:
            key, value = piece.split("=", 1)
            parts[key.strip().upper()] = value.strip()
    freq = parts.get("FREQ", "").upper()
    if (
        freq not in ("DAILY", "WEEKLY")
        or _UNSUPPORTED_PARTS & parts.keys()
        or parts.get("INTERVAL", "1") != "1"
        or any(len(parts.get(k, "").split(",")) > 1 for k in ("BYHOUR", "BYMINUTE"))
        or any(
            re.search(r"\d", d) for d in parts.get("BYDAY", "").split(",")
        )
    ):
        return rrule
    text = "daily"
    if freq == "WEEKLY":
        days = [_DAYS.get(d.strip().upper()[-2:]) for d in parts.get("BYDAY", "").split(",") if d.strip()]
        if any(d is None for d in days):
            return rrule
        text = "weekly on " + ", ".join(days) if days else "weekly"
    at = _time_of_day(parts, rrule, start_time)
    return f"{text} at {at}" if at else text


def build_search_text(
    agent: AgentRecord, contacts: List[ContactRecord], triggers: List[TriggerRecord]
) -> str:
    """Text the FTS and embedding indexes see for one agent."""
    pieces = [agent.name, agent.description]
    for c in contacts:
        pieces.extend([c.display_name, c.email])
    for t in triggers:
        if t.status != "active":
            continue
        pieces.append(t.payload)
        if t.recurrence_rule:
            pieces.append(describe_schedule(t.recurrence_rule, t.start_time))
    return "\n".join(p for p in pieces if p)
