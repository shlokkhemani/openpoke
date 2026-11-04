from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from html import escape, unescape
from pathlib import Path
from typing import List, Optional, Tuple

from ....data_paths import get_data_dir
from ....logging_config import logger
from ....utils.timezones import now_in_user_timezone
from .state import LogEntry, SummaryState


_DATA_DIR = get_data_dir()
_WORKING_MEMORY_LOG_PATH = _DATA_DIR / "conversation" / "poke_working_memory.log"


def _encode_payload(payload: str) -> str:
    normalized = payload.replace("\r\n", "\n").replace("\r", "\n")
    collapsed = normalized.replace("\n", "\\n")
    return escape(collapsed, quote=False)


def _decode_payload(payload: str) -> str:
    return unescape(payload).replace("\\n", "\n")


def _format_line(tag: str, payload: str, timestamp: Optional[str] = None) -> str:
    encoded = _encode_payload(payload)
    if timestamp:
        return f"<{tag} timestamp=\"{timestamp}\">{encoded}</{tag}>\n"
    return f"<{tag}>{encoded}</{tag}>\n"


def _current_timestamp() -> str:
    return now_in_user_timezone("%Y-%m-%d %H:%M:%S")


class WorkingMemoryLog:
    """Persisted working-memory file storing conversation summary and recent entries."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._ensure_directory()
        self._initialize_file()

    def _ensure_directory(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "working memory directory creation failed",
                extra={"error": str(exc), "path": str(self._path)},
            )

    def _initialize_file(self) -> None:
        with self._lock:
            self._initialize_file_locked()

    def _initialize_file_locked(self) -> None:
        if self._path.exists() and self._path.stat().st_size > 0:
            return
        initial_state = SummaryState.empty()
        lines = [
            _format_line(
                "summary_info",
                json.dumps({"last_index": initial_state.last_index, "updated_at": None}),
            ),
            _format_line("conversation_summary", ""),
        ]
        try:
            self._path.write_text("".join(lines), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "working memory initialization failed",
                extra={"error": str(exc), "path": str(self._path)},
            )
            raise

    def append_entry(self, tag: str, payload: str, timestamp: Optional[str] = None) -> None:
        sanitized_timestamp = timestamp or _current_timestamp()
        line = _format_line(tag, str(payload), sanitized_timestamp)
        with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "working memory append failed",
                    extra={"error": str(exc), "tag": tag, "path": str(self._path)},
                )
                raise

    def load_summary_state(self) -> SummaryState:
        with self._lock:
            try:
                lines = self._path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                return SummaryState.empty()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "working memory read failed",
                    extra={"error": str(exc), "path": str(self._path)},
                )
                return SummaryState.empty()

        summary_text = ""
        last_index = -1
        updated_at: Optional[datetime] = None
        entries: List[LogEntry] = []

        for raw_line in lines:
            parsed = self._parse_line(raw_line)
            if parsed is None:
                continue
            tag, timestamp, payload = parsed
            if tag == "summary_info":
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                last_index_val = data.get("last_index")
                if isinstance(last_index_val, int):
                    last_index = last_index_val
                updated_raw = data.get("updated_at")
                if isinstance(updated_raw, str) and updated_raw:
                    try:
                        updated_at = datetime.fromisoformat(updated_raw)
                    except ValueError:
                        updated_at = None
            elif tag == "conversation_summary":
                summary_text = payload
            else:
                entries.append(
                    LogEntry(tag=tag, payload=payload, timestamp=timestamp or None)
                )

        state = SummaryState(
            summary_text=summary_text,
            last_index=last_index,
            updated_at=updated_at,
            unsummarized_entries=entries,
        )
        return state

    def write_summary_state(self, state: SummaryState) -> None:
        meta_payload = json.dumps(
            {
                "last_index": state.last_index,
                "updated_at": state.updated_at.isoformat() if state.updated_at else None,
            }
        )

        lines = [_format_line("summary_info", meta_payload)]
        lines.append(_format_line("conversation_summary", state.summary_text or ""))
        for entry in state.unsummarized_entries:
            lines.append(_format_line(entry.tag, entry.payload, entry.timestamp))

        temp_path = self._path.with_suffix(".tmp")
        data = "".join(lines)
        with self._lock:
            try:
                temp_path.write_text(data, encoding="utf-8")
                temp_path.replace(self._path)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "working memory write failed",
                    extra={"error": str(exc), "path": str(self._path)},
                )
                raise
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:  # pragma: no cover - defensive cleanup
                        pass

    def render_transcript(self, state: Optional[SummaryState] = None) -> str:
        snapshot = state or self.load_summary_state()
        parts: List[str] = []

        summary_text = (snapshot.summary_text or "").strip()
        if summary_text:
            safe_summary = escape(summary_text, quote=False)
            parts.append(f"<conversation_summary>{safe_summary}</conversation_summary>")

        for entry in snapshot.unsummarized_entries:
            safe_payload = escape(entry.payload, quote=False)
            if entry.timestamp:
                parts.append(
                    f'<{entry.tag} timestamp="{entry.timestamp}">{safe_payload}</{entry.tag}>'
                )
            else:
                parts.append(f'<{entry.tag}>{safe_payload}</{entry.tag}>')

        return '\n'.join(parts)

    def clear(self) -> None:
        with self._lock:
            try:
                if self._path.exists():
                    self._path.unlink()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "working memory clear failed",
                    extra={"error": str(exc), "path": str(self._path)},
                )
            finally:
                self._ensure_directory()
                self._initialize_file_locked()

    def _parse_line(self, line: str) -> Optional[Tuple[str, Optional[str], str]]:
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
        timestamp = None
        if attr_string:
            match = re.search(r'timestamp="([^"]*)"', attr_string)
            if match:
                timestamp = match.group(1)
        return tag, timestamp, _decode_payload(payload)


_working_memory_log: Optional[WorkingMemoryLog] = None
_factory_lock = threading.Lock()


def get_working_memory_log() -> WorkingMemoryLog:
    global _working_memory_log
    if _working_memory_log is None:
        with _factory_lock:
            if _working_memory_log is None:
                _working_memory_log = WorkingMemoryLog(_WORKING_MEMORY_LOG_PATH)
    return _working_memory_log


__all__ = ["WorkingMemoryLog", "get_working_memory_log"]
