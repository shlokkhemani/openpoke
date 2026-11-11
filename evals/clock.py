"""Fixed eval clock. All ``*_days_ago`` fields are relative to EVAL_NOW."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

EVAL_NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


def days_ago(d: float) -> datetime:
    return EVAL_NOW - timedelta(days=d)
