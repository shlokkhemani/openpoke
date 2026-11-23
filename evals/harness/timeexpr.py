"""Resolve the relative time expressions used in scenario checks.

Supported (case-insensitive), each with an optional trailing IANA timezone (e.g. "Europe/Berlin"):
    today HH:MM            tomorrow HH:MM
    <weekday> HH:MM        the next such weekday+time strictly after `now` (may be today)
    next <weekday> HH:MM   that weekday on a later date than today (never today)
    next weekday HH:MM     the next Mon-Fri at HH:MM strictly after `now`
    now + N min            N minutes after `now`
    in N days HH:MM        N calendar days after today, at HH:MM
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_TZ = re.compile(r"\s+([A-Za-z]+/[A-Za-z_]+(?:/[A-Za-z_]+)?)$")
_HHMM = r"(\d{1,2}):(\d{2})"


def resolve(expr: str, now: datetime, default_tz: str) -> datetime:
    """Return an aware datetime for `expr`, relative to `now`."""
    text = expr.strip()
    tz_name = default_tz
    match = _TZ.search(text)
    if match:
        tz_name = match.group(1)
        text = text[: match.start()].strip()
    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    lower = text.lower()

    m = re.fullmatch(r"now\s*\+\s*(\d+)\s*min(?:ute)?s?", lower)
    if m:
        return local_now + timedelta(minutes=int(m.group(1)))

    m = re.fullmatch(rf"in\s+(\d+)\s+days?\s+{_HHMM}", lower)
    if m:
        return _at(local_now.date() + timedelta(days=int(m.group(1))), int(m.group(2)), int(m.group(3)), tz)

    m = re.fullmatch(rf"(today|tomorrow)\s+{_HHMM}", lower)
    if m:
        day = local_now.date() + timedelta(days=1 if m.group(1) == "tomorrow" else 0)
        return _at(day, int(m.group(2)), int(m.group(3)), tz)

    m = re.fullmatch(rf"next weekday\s+{_HHMM}", lower)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        for offset in range(0, 8):
            candidate = _at(local_now.date() + timedelta(days=offset), hour, minute, tz)
            if candidate.weekday() < 5 and candidate > local_now:
                return candidate

    m = re.fullmatch(rf"(next\s+)?({'|'.join(WEEKDAYS)})\s+{_HHMM}", lower)
    if m:
        strict_later_day = bool(m.group(1))
        target = WEEKDAYS.index(m.group(2))
        hour, minute = int(m.group(3)), int(m.group(4))
        for offset in range(0, 15):
            day = local_now.date() + timedelta(days=offset)
            if day.weekday() != target or (strict_later_day and offset == 0):
                continue
            candidate = _at(day, hour, minute, tz)
            if candidate > local_now:
                return candidate

    raise ValueError(f"unsupported time expression: {expr!r}")


def _at(day, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)


def parse_storage(ts: str | None) -> datetime | None:
    """Parse a triggers.db timestamp ('2026-11-22T17:00:00Z')."""
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


__all__ = ["resolve", "parse_storage", "WEEKDAYS"]
