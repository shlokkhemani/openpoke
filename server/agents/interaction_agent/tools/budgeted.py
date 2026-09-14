"""Budgeted-only interaction-agent tools."""

from __future__ import annotations

from typing import Optional

from ....config import get_settings
from ....context.digest import digest_many
from ....logging_config import logger
from ....services.conversation import get_conversation_log
from ..context.history import recall_entries
from .types import ToolResult

RECALL_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "recall_history",
        "description": (
            "Fetch the full text of earlier conversation entries that are shown only as an index line or a "
            "truncated preview. Use it before acting on details you cannot see verbatim (draft bodies, thread or "
            "draft IDs, exact rules, pasted content). Pass entry_ids for specific entries, or query to search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entry_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Entry ids from the history (the id=\"N\" attribute or the [N] index prefix).",
                },
                "query": {
                    "type": "string",
                    "description": "Case-insensitive text to search for across all history; returns the most recent matches.",
                },
                "limit": {"type": "integer", "description": "Max entries to return for a query (default 5)."},
                "offset_chars": {
                    "type": "integer",
                    "description": "For a single very large entry: character offset to continue reading from.",
                },
            },
            "additionalProperties": False,
        },
    },
}

DIGEST_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "digest_entry",
        "description": (
            "Read ONE large conversation entry in full, outside your context, and return a compact answer to a question "
            "about it (summary, key terms, a specific figure, each side's position). Use it for synthesis over an entry "
            "shown truncated or indexed: a long worker report, a pasted document, a merged batch of results. Do NOT use it "
            "for content that must be preserved verbatim (a draft to show or send): pass that by id instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entry_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "One or more conversation entry ids (from the index, a truncated tag, or a preview header). "
                        "Several ids are digested separately and combined."
                    ),
                },
                "question": {
                    "type": "string",
                    "description": "What you need from the entries. Ask for everything you need in one call.",
                },
            },
            "required": ["entry_ids", "question"],
            "additionalProperties": False,
        },
    },
}

FIND_WORKER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "find_worker",
        "description": (
            "Look up existing workers by a few words about the task, counterpart or an identifier (draft/thread id). "
            "Returns the best matches with their purpose, last task, last use and identifiers, so you can reuse "
            "the right one instead of creating a new worker."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max matches (default 5)."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

SEND_DRAFT_V2_SCHEMA = {
    "type": "function",
    "function": {
        "name": "send_draft_v2",
        "description": (
            "Show the user a draft that a worker created, by its draft id, with a short preview. Use this instead of "
            "send_draft when the worker reported a draft id; the full body stays in Gmail and is sent by id later."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string"},
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body_preview": {
                    "type": "string",
                    "description": "At most ~300 characters of the body, as the worker reported it.",
                },
            },
            "required": ["draft_id", "to", "subject"],
            "additionalProperties": False,
        },
    },
}


def find_worker(query: str, limit: int = 5) -> ToolResult:
    from ....services.execution.roster_v2 import get_roster_meta

    meta = get_roster_meta()
    matches = meta.search(query or "", int(limit or 5))
    return ToolResult(
        success=True,
        payload={
            "matches": matches,
            "total_workers": len(meta.all_names()),
            "note": "" if matches else "no worker matches; create a new one named topic + counterpart",
        },
    )


def recall_history(
    entry_ids: Optional[list] = None,
    query: Optional[str] = None,
    limit: int = 5,
    offset_chars: int = 0,
) -> ToolResult:
    """Return full conversation entries by id or search query."""
    if not entry_ids and not (query or "").strip():
        return ToolResult(success=False, payload={"error": "Provide entry_ids or a query."})
    try:
        payload = recall_entries(
            entry_ids=entry_ids,
            query=query,
            limit=int(limit or 5),
            offset_chars=int(offset_chars or 0),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("recall_history failed", extra={"error": str(exc)})
        return ToolResult(success=False, payload={"error": "recall failed"})
    return ToolResult(success=True, payload=payload)


async def digest_entry(entry_ids=None, question: str = "", entry_id=None) -> ToolResult:
    settings = get_settings()
    raw_ids = list(entry_ids or []) + ([entry_id] if entry_id is not None else [])
    ids: list = []
    for raw in raw_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            return ToolResult(success=False, payload={"error": f"entry id {raw!r} is not an integer"})
    if not ids:
        return ToolResult(success=False, payload={"error": "entry_ids is required"})
    if not (question or "").strip():
        return ToolResult(success=False, payload={"error": "question is required"})
    entries = list(get_conversation_log().iter_entries())
    items = []
    for idx in ids:
        if idx < 0 or idx >= len(entries):
            return ToolResult(success=False, payload={"error": f"no entry with id {idx}"})
        tag, ts, payload = entries[idx]
        items.append((f"conversation entry {idx} ({tag} {ts})", payload))
    try:
        out = await digest_many(
            items,
            question,
            model=settings.execution_agent_search_model,
            api_key=settings.openrouter_api_key,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("digest_entry failed", extra={"error": str(exc)})
        return ToolResult(success=False, payload={"error": f"digest failed: {exc}"})
    return ToolResult(
        success=True,
        payload={"entry_ids": ids, "total_chars": sum(len(t) for _, t in items), **out},
    )


def send_draft_v2(draft_id: str, to: str, subject: str, body_preview: str = "") -> ToolResult:
    log = get_conversation_log()
    preview = (body_preview or "").strip()
    message = f"To: {to}\nSubject: {subject}\nDraft: {draft_id}\n\n{preview}" + ("\n[...]" if preview else "")
    log.record_reply(message)
    return ToolResult(
        success=True,
        payload={"status": "draft_recorded", "draft_id": draft_id, "to": to, "subject": subject},
        recorded_reply=True,
    )


def budgeted_schemas():
    """Schemas to append when budgeted_context is active."""
    settings = get_settings()
    schemas = [RECALL_TOOL_SCHEMA, SEND_DRAFT_V2_SCHEMA]
    if settings.roster_v2_enabled:
        schemas.append(FIND_WORKER_SCHEMA)
    if settings.interaction_digest_enabled:
        schemas.append(DIGEST_TOOL_SCHEMA)
    return schemas


__all__ = [
    "DIGEST_TOOL_SCHEMA",
    "FIND_WORKER_SCHEMA",
    "RECALL_TOOL_SCHEMA",
    "SEND_DRAFT_V2_SCHEMA",
    "budgeted_schemas",
    "digest_entry",
    "find_worker",
    "recall_history",
    "send_draft_v2",
]
