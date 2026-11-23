"""Execution-log compaction (problems-and-solutions §2).

When an agent's log has more than COMPACT_THRESHOLD unsummarized entries, the oldest ones are folded
into a task summary (stored next to the log as `<slug>.summary.json`) and only the most recent
KEEP_TAIL entries stay verbatim in the agent's system prompt.
"""

from __future__ import annotations

import asyncio
import json
from html import escape
from typing import List, Optional, Set, Tuple

from ...config import get_settings
from ...logging_config import logger
from ...openrouter_client import request_chat_completion
from ...services.execution import get_execution_agent_logs

COMPACT_THRESHOLD = 40
KEEP_TAIL = 10

_in_progress: Set[str] = set()

_SYSTEM_PROMPT = (
    "You maintain the working memory of a task-execution agent. Merge the existing task summary with the new "
    "log entries into an updated summary. Output plain text with these sections:\n"
    "Goal: what the task is for.\n"
    "Decisions: what was done or decided (times, recipients, schedules), most recent state wins.\n"
    "Open items: anything pending, waiting, or unresolved.\n"
    "Key IDs: trigger IDs, thread IDs, draft IDs, email addresses, with what each refers to.\n"
    "Be concise and factual. Drop superseded details."
)


def _load_summary(agent_name: str) -> Tuple[str, int]:
    path = get_execution_agent_logs().summary_path(agent_name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("summary") or ""), int(data.get("last_index", -1))
    except FileNotFoundError:
        return "", -1
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("failed to read execution summary", extra={"agent": agent_name, "error": str(exc)})
        return "", -1


def _save_summary(agent_name: str, summary: str, last_index: int) -> None:
    path = get_execution_agent_logs().summary_path(agent_name)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"summary": summary, "last_index": last_index}), encoding="utf-8")
    tmp.replace(path)


def _format_entry(tag: str, timestamp: str, payload: str) -> str:
    safe = escape(payload, quote=False)
    return f'<{tag} timestamp="{timestamp}">{safe}</{tag}>' if timestamp else f"<{tag}>{safe}</{tag}>"


def render_history(agent_name: str) -> str:
    """Return the compacted history: task summary (if any) plus verbatim recent entries."""
    summary, last_index = _load_summary(agent_name)
    entries = list(get_execution_agent_logs().iter_entries(agent_name))
    parts: List[str] = []
    if summary.strip():
        parts.append(f"<task_summary>{escape(summary.strip(), quote=False)}</task_summary>")
    parts.extend(_format_entry(*entry) for i, entry in enumerate(entries) if i > last_index)
    return "\n".join(parts)


async def maybe_compact(agent_name: str) -> bool:
    """Fold old entries into the task summary if the log is over the threshold."""
    if agent_name in _in_progress:
        return False
    summary, last_index = _load_summary(agent_name)
    entries = list(get_execution_agent_logs().iter_entries(agent_name))
    unsummarized = [(i, e) for i, e in enumerate(entries) if i > last_index]
    if len(unsummarized) <= COMPACT_THRESHOLD:
        return False

    batch = unsummarized[:-KEEP_TAIL]
    new_last_index = batch[-1][0]
    lines = "\n".join(f"[{i}] {tag}: {payload}" for i, (tag, _ts, payload) in batch)
    content = f"Existing task summary:\n{summary or 'None'}\n\nNew log entries to merge:\n{lines}"

    settings = get_settings()
    _in_progress.add(agent_name)
    try:
        response = await request_chat_completion(
            model=settings.summarizer_model,
            messages=[{"role": "user", "content": content}],
            system=_SYSTEM_PROMPT,
            api_key=settings.openrouter_api_key,
        )
        text = ((response.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if not text.strip():
            return False
        _save_summary(agent_name, text.strip(), new_last_index)
        logger.info("execution log compacted", extra={"agent": agent_name, "folded": len(batch)})
        return True
    except Exception as exc:
        logger.warning("execution log compaction failed", extra={"agent": agent_name, "error": str(exc)})
        return False
    finally:
        _in_progress.discard(agent_name)


def schedule_compaction(agent_name: str) -> Optional[asyncio.Task]:
    """Run `maybe_compact` in the background (no-op without a running loop)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    return loop.create_task(maybe_compact(agent_name))


__all__ = ["render_history", "maybe_compact", "schedule_compaction", "COMPACT_THRESHOLD", "KEEP_TAIL"]
