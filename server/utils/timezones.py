"""Shared helpers for working with the user's preferred timezone."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..benchmark_clock import benchmark_clock_enabled, get_benchmark_clock
from ..logging_config import logger
from ..services.timezone_store import get_timezone_store

UTC = timezone.utc


def get_user_timezone_name(default: str = "UTC") -> str:
    """Return the stored timezone preference or a default."""

    store = get_timezone_store()
    return store.get_timezone(default)


def resolve_user_timezone(default: str = "UTC") -> ZoneInfo:
    """Resolve the stored timezone to a ZoneInfo, falling back to default on error."""

    tz_name = get_user_timezone_name(default)
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning(
            "unknown timezone; defaulting to %s",
            default,
            extra={"timezone": tz_name},
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "timezone resolution failed; defaulting to %s",
            default,
            extra={"error": str(exc)},
        )
    return ZoneInfo(default)


def now_in_user_timezone(fmt: Optional[str] = None, *, default: str = "UTC") -> datetime | str:
    """Return the current time in the user's timezone.

    When *fmt* is provided, the result is formatted using ``datetime.strftime``;
    otherwise the aware ``datetime`` object is returned.
    """

    if benchmark_clock_enabled():
        current = get_benchmark_clock().now_utc().astimezone(
            resolve_user_timezone(default)
        )
    else:
        current = datetime.now(resolve_user_timezone(default))
    if fmt is None:
        return current
    return current.strftime(fmt)


def convert_to_user_timezone(dt: datetime, *, default: str = "UTC") -> datetime:
    """Convert *dt* into the user's timezone with UTC fallback."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    tz = resolve_user_timezone(default)
    try:
        return dt.astimezone(tz)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "timezone conversion failed; defaulting to %s",
            default,
            extra={"error": str(exc)},
        )
        return dt.astimezone(ZoneInfo(default))


__all__ = [
    "UTC",
    "convert_to_user_timezone",
    "get_user_timezone_name",
    "now_in_user_timezone",
    "resolve_user_timezone",
]
