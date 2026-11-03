"""Background watcher that surfaces important Gmail emails proactively."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from .client import execute_gmail_tool, get_active_gmail_user_id
from .processing import EmailTextCleaner, ProcessedEmail, parse_gmail_fetch_response
from .seen_store import GmailSeenStore
from .importance_classifier import classify_email_importance
from ...data_paths import get_data_dir
from ...logging_config import logger
from ...utils.timezones import convert_to_user_timezone


if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime


def _resolve_interaction_runtime() -> "InteractionAgentRuntime":
    from ...agents.interaction_agent.runtime import InteractionAgentRuntime

    return InteractionAgentRuntime()


DEFAULT_POLL_INTERVAL_SECONDS = 60.0
DEFAULT_LOOKBACK_MINUTES = 10
DEFAULT_MAX_RESULTS = 50
DEFAULT_SEEN_LIMIT = 300


_DATA_DIR = get_data_dir()
_DEFAULT_SEEN_PATH = _DATA_DIR / "gmail_seen.json"


class ImportantEmailWatcher:
    """Poll Gmail for recent messages and surface important ones."""

    def __init__(
        self,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
        *,
        seen_store: Optional[GmailSeenStore] = None,
    ) -> None:
        self._poll_interval = poll_interval_seconds
        self._lookback_minutes = lookback_minutes
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._seen_store = seen_store or GmailSeenStore(_DEFAULT_SEEN_PATH, DEFAULT_SEEN_LIMIT)
        self._cleaner = EmailTextCleaner(max_url_length=60)
        self._has_seeded_initial_snapshot = False
        self._last_poll_timestamp: Optional[datetime] = None

    # Start the background email polling task
    async def start(self) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                return
            loop = asyncio.get_running_loop()
            self._running = True
            self._has_seeded_initial_snapshot = False
            self._last_poll_timestamp = None
            self._task = loop.create_task(self._run(), name="important-email-watcher")
            logger.info(
                "Important email watcher started",
                extra={"interval_seconds": self._poll_interval, "lookback_minutes": self._lookback_minutes},
            )

    # Stop the background email polling task gracefully
    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                finally:
                    self._task = None
                logger.info("Important email watcher stopped")

    async def _run(self) -> None:
        try:
            while self._running:
                try:
                    await self._poll_once()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("Important email watcher poll failed", extra={"error": str(exc)})
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            raise

    # Poll Gmail once for new messages and classify them for importance
    def _complete_poll(self, user_now: datetime) -> None:
        self._last_poll_timestamp = user_now
        self._has_seeded_initial_snapshot = True

    async def _poll_once(self) -> None:
        poll_started_at = datetime.now(timezone.utc)
        user_now = convert_to_user_timezone(poll_started_at)
        first_poll = not self._has_seeded_initial_snapshot
        previous_poll_timestamp = self._last_poll_timestamp
        interval_cutoff = user_now - timedelta(seconds=self._poll_interval)
        cutoff_time = interval_cutoff
        if previous_poll_timestamp is not None and previous_poll_timestamp > interval_cutoff:
            cutoff_time = previous_poll_timestamp

        composio_user_id = get_active_gmail_user_id()
        if not composio_user_id:
            logger.debug("Gmail not connected; skipping importance poll")
            return

        query = f"label:INBOX newer_than:{self._lookback_minutes}m"
        arguments = {
            "query": query,
            "include_payload": True,
            "max_results": DEFAULT_MAX_RESULTS,
        }

        try:
            raw_result = execute_gmail_tool("GMAIL_FETCH_EMAILS", composio_user_id, arguments=arguments)
        except Exception as exc:
            logger.warning(
                "Failed to fetch Gmail messages for watcher",
                extra={"error": str(exc)},
            )
            return

        processed_emails, _ = parse_gmail_fetch_response(
            raw_result,
            query=query,
            cleaner=self._cleaner,
        )

        if not processed_emails:
            logger.debug("No recent Gmail messages found for watcher")
            self._complete_poll(user_now)
            return

        if first_poll:
            self._seen_store.mark_seen(email.id for email in processed_emails)
            logger.info(
                "Important email watcher completed initial warmup",
                extra={"skipped_ids": len(processed_emails)},
            )
            self._complete_poll(user_now)
            return

        unseen_emails: List[ProcessedEmail] = [
            email for email in processed_emails if not self._seen_store.is_seen(email.id)
        ]

        if not unseen_emails:
            logger.info(
                "Important email watcher check complete",
                extra={"emails_reviewed": 0, "surfaced": 0},
            )
            self._complete_poll(user_now)
            return

        unseen_emails.sort(key=lambda email: email.timestamp or datetime.now(timezone.utc))

        eligible_emails: List[ProcessedEmail] = []
        aged_emails: List[ProcessedEmail] = []

        for email in unseen_emails:
            email_timestamp = email.timestamp
            if email_timestamp.tzinfo is not None:
                email_timestamp = email_timestamp.astimezone(user_now.tzinfo)
            else:
                email_timestamp = email_timestamp.replace(tzinfo=user_now.tzinfo)

            if email_timestamp < cutoff_time:
                aged_emails.append(email)
                continue

            eligible_emails.append(email)

        if not eligible_emails and aged_emails:
            self._seen_store.mark_seen(email.id for email in aged_emails)
            logger.info(
                "Important email watcher check complete",
                extra={
                    "emails_reviewed": len(unseen_emails),
                    "surfaced": 0,
                    "suppressed_for_age": len(aged_emails),
                },
            )
            self._complete_poll(user_now)
            return

        summaries_sent = 0
        processed_ids: List[str] = [email.id for email in aged_emails]

        for email in eligible_emails:
            summary = await classify_email_importance(email)
            processed_ids.append(email.id)
            if not summary:
                continue

            summaries_sent += 1
            await self._dispatch_summary(summary)

        if processed_ids:
            self._seen_store.mark_seen(processed_ids)

        logger.info(
            "Important email watcher check complete",
            extra={
                "emails_reviewed": len(unseen_emails),
                "surfaced": summaries_sent,
                "suppressed_for_age": len(aged_emails),
            },
        )
        self._complete_poll(user_now)

    async def _dispatch_summary(self, summary: str) -> None:
        runtime = _resolve_interaction_runtime()
        try:
            contextualized = f"Important email watcher notification:\n{summary}"
            await runtime.handle_agent_message(contextualized)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to dispatch important email summary",
                extra={"error": str(exc)},
            )


_watcher_instance: Optional[ImportantEmailWatcher] = None


def get_important_email_watcher() -> ImportantEmailWatcher:
    global _watcher_instance
    if _watcher_instance is None:
        _watcher_instance = ImportantEmailWatcher()
    return _watcher_instance


__all__ = ["ImportantEmailWatcher", "get_important_email_watcher"]
