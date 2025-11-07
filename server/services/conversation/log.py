from __future__ import annotations

import asyncio
import re
from html import escape, unescape
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Protocol, Tuple, cast

from ...config import get_settings
from ...logging_config import logger
from ...utils.exceptions import ConversationLogError
from ...models import ChatMessage
from ...utils.timezones import now_in_user_timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - used for type checkers only
    from .summarization.working_memory_log import WorkingMemoryLog


_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_CONVERSATION_LOG_PATH = _DATA_DIR / "conversation" / "alyn_conversation.log"


class TranscriptFormatter(Protocol):
    def __call__(self, tag: str, timestamp: str, payload: str) -> str:  # pragma: no cover - typing protocol
        ...


def _encode_payload(payload: str) -> str:
    normalized = payload.replace("\r\n", "\n").replace("\r", "\n")
    collapsed = normalized.replace("\n", "\\n")
    return escape(collapsed, quote=False)


def _decode_payload(payload: str) -> str:
    return unescape(payload).replace("\\n", "\n")


def _default_formatter(tag: str, timestamp: str, payload: str) -> str:
    encoded = _encode_payload(payload)
    return f"<{tag} timestamp=\"{timestamp}\">{encoded}</{tag}>\n"


def _resolve_working_memory_log() -> "WorkingMemoryLog":
    from .summarization import get_working_memory_log

    return get_working_memory_log()


_ATTR_PATTERN = re.compile(r"(\w+)\s*=\s*\"([^\"]*)\"")


class ConversationLog:
    """Append-only conversation log persisted to disk for the interaction agent.

    Thread-safety: This class is async-safe using asyncio.Lock:
    - _lock protects all file I/O operations to prevent concurrent access
    - All methods that access the log file must acquire the lock
    - Uses async context manager (async with) for proper lock handling
    """

    def __init__(self, path: Path, formatter: TranscriptFormatter = _default_formatter):
        self._path = path
        self._formatter = formatter
        self._lock = asyncio.Lock()
        self._ensure_directory()
        self._working_memory_log = _resolve_working_memory_log()

    def _ensure_directory(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - defensive
            logger.warning("conversation log directory creation failed", extra={"error": str(exc)})

    async def _append(self, tag: str, payload: str) -> str:
        """Append an entry to the conversation log.

        Thread-safety: Acquires _lock to ensure atomic file writes and
        prevent concurrent access corruption.
        """
        timestamp = cast(str, now_in_user_timezone("%Y-%m-%d %H:%M:%S"))
        entry = self._formatter(tag, timestamp, str(payload))
        async with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(entry)
            except OSError as exc:  # pragma: no cover - defensive
                logger.error(
                    "conversation log append failed",
                    extra={"error": str(exc), "tag": tag, "path": str(self._path)},
                )
                raise ConversationLogError(
                    "Failed to append to conversation log",
                    operation="append",
                ) from exc
        self._notify_summarization()
        return timestamp

    def _parse_line(self, line: str) -> Optional[Tuple[str, str, str]]:
        stripped = line.strip()
        if not stripped.startswith("<") or "</" not in stripped:
            return None
        open_end = stripped.find(">")
        if open_end == -1:
            return None
        open_tag_content = stripped[1:open_end]
        if " " in open_tag_content:
            tag, attr_string = open_tag_content.split(" ", 1)
        else:
            tag, attr_string = open_tag_content, ""
        close_start = stripped.rfind("</")
        close_end = stripped.rfind(">")
        if close_start == -1 or close_end == -1:
            return None
        closing_tag = stripped[close_start + 2 : close_end]
        if closing_tag != tag:
            return None
        payload = stripped[open_end + 1 : close_start]
        attributes: Dict[str, str] = {
            match.group(1): match.group(2) for match in _ATTR_PATTERN.finditer(attr_string)
        }
        timestamp = attributes.get("timestamp", "")
        return tag, timestamp, _decode_payload(payload)

    async def iter_entries(self) -> AsyncIterator[Tuple[str, str, str]]:
        """Iterate over all entries in the conversation log.

        Thread-safety: Acquires _lock to ensure consistent read of log file
        and prevent reading while another operation is writing.
        """
        async with self._lock:
            try:
                lines = self._path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                lines = []
            except OSError as exc:  # pragma: no cover - defensive
                logger.error(
                    "conversation log read failed", extra={"error": str(exc), "path": str(self._path)}
                )
                raise ConversationLogError("Failed to read conversation log", operation="read") from exc
        for line in lines:
            item = self._parse_line(line)
            if item is not None:
                yield item

    async def load_transcript(self) -> str:
        """Load the full transcript as an XML string.

        Thread-safety: Delegates to iter_entries which handles locking.
        """
        parts: List[str] = []
        async for tag, timestamp, payload in self.iter_entries():
            safe_payload = escape(payload, quote=False)
            if timestamp:
                parts.append(f"<{tag} timestamp=\"{timestamp}\">{safe_payload}</{tag}>")
            else:
                parts.append(f"<{tag}>{safe_payload}</{tag}>")
        return "\n".join(parts)

    async def record_user_message(self, content: str) -> None:
        """Record a user message to the conversation log."""
        timestamp = await self._append("user_message", content)
        self._working_memory_log.append_entry("user_message", content, timestamp)

    async def record_agent_message(self, content: str) -> None:
        """Record an agent message to the conversation log."""
        timestamp = await self._append("agent_message", content)
        self._working_memory_log.append_entry("agent_message", content, timestamp)

    async def record_reply(self, content: str) -> None:
        """Record an assistant reply to the conversation log."""
        timestamp = await self._append("alyn_reply", content)
        self._working_memory_log.append_entry("alyn_reply", content, timestamp)

    async def record_wait(self, reason: str) -> None:
        """Record a wait marker that should not reach the user-facing chat history."""
        timestamp = await self._append("wait", reason)
        self._working_memory_log.append_entry("wait", reason, timestamp)

    def _notify_summarization(self) -> None:
        settings = get_settings()
        if not settings.summarization_enabled:
            return

        try:
            from .summarization import schedule_summarization  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover - defensive
            logger.debug(
                "summarization scheduler unavailable",
                extra={"error": str(exc)},
            )
            return

        try:
            schedule_summarization()
        except (RuntimeError, ConversationLogError) as exc:  # pragma: no cover - defensive
            logger.warning(
                "failed to schedule summarization",
                extra={"error": str(exc)},
            )
        except OSError as exc:  # pragma: no cover - defensive
            logger.warning(
                "failed to schedule summarization due to I/O error",
                extra={"error": str(exc)},
            )

    async def to_chat_messages(self) -> List[ChatMessage]:
        """Convert log entries to ChatMessage format.

        Thread-safety: Delegates to iter_entries which handles locking.
        """
        messages: List[ChatMessage] = []
        async for tag, timestamp, payload in self.iter_entries():
            normalized_timestamp = timestamp or None
            if tag == "user_message":
                messages.append(
                    ChatMessage(role="user", content=payload, timestamp=normalized_timestamp)
                )
            elif tag == "alyn_reply":
                messages.append(
                    ChatMessage(
                        role="assistant", content=payload, timestamp=normalized_timestamp
                    )
                )
            elif tag == "wait":
                # Wait markers are orchestration metadata and must not surface to the user
                continue
        return messages

    async def clear(self) -> None:
        """Clear the conversation log.

        Thread-safety: Acquires _lock to ensure atomic clear operation
        and prevent concurrent access during deletion.
        """
        async with self._lock:
            try:
                if self._path.exists():
                    self._path.unlink()
            except OSError as exc:  # pragma: no cover - defensive
                logger.warning(
                    "conversation log clear failed", extra={"error": str(exc), "path": str(self._path)}
                )
            finally:
                self._ensure_directory()
        try:
            self._working_memory_log.clear()
        except (RuntimeError, ConversationLogError) as exc:  # pragma: no cover - defensive
            logger.debug(
                "working memory clear skipped",
                extra={"error": str(exc)},
            )
        except OSError as exc:  # pragma: no cover - defensive
            logger.debug(
                "working memory clear encountered I/O error",
                extra={"error": str(exc)},
            )


_conversation_log = ConversationLog(_CONVERSATION_LOG_PATH)


def get_conversation_log() -> ConversationLog:
    return _conversation_log


__all__ = ["ConversationLog", "get_conversation_log"]
