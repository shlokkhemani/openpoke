"""Per-run bounded tool results for the budgeted execution agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ....config import get_settings
from ....context.digest import digest_text
from ....context.preview import preview_text
from ....utils.tokens import chars_for_tokens, estimate_tokens


def _is_email_list(payload: Any) -> bool:
    return (
        isinstance(payload, list)
        and payload
        and all(isinstance(x, dict) and "id" in x and "clean_text" in x for x in payload)
    )


@dataclass
class ResultStore:
    emails: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    results: Dict[str, str] = field(default_factory=dict)
    pages_read: int = 0
    spent_tokens: int = 0

    def nothing_new(self, payload: Any) -> bool:
        """True when every email in a search result is already in the store (id-based cache hit)."""
        if not _is_email_list(payload):
            return False
        return all(str(e.get("id")) in self.emails for e in payload)

    def remember(self, call_id: str, payload: Any) -> None:
        try:
            self.results[call_id] = payload if isinstance(payload, str) else json.dumps(payload, default=str)
        except Exception:
            self.results[call_id] = str(payload)
        if _is_email_list(payload):
            for e in payload:
                self.emails[str(e["id"])] = e

    def bound(self, payload: Any, *, per_email_tokens: int, total_tokens: int) -> Any:
        """Return a copy of payload safe to put in a prompt."""
        if _is_email_list(payload):
            out = []
            for e in payload:
                text = e.get("clean_text") or ""
                item = dict(e)
                if estimate_tokens(text) > per_email_tokens:
                    item["clean_text"] = preview_text(
                        text,
                        per_email_tokens,
                        note=(
                            f"{len(text):,} chars total; call read_email(message_id) to page or "
                            "digest_email(message_id, question) to read it all"
                        ),
                    )
                    item["clean_text_truncated"] = True
                    item["clean_text_total_chars"] = len(text)
                out.append(item)
            payload = out
        serialized = payload if isinstance(payload, str) else json.dumps(payload, default=str)
        settings = get_settings()
        run_budget = settings.tool_result_run_budget_tokens
        remaining = max(1_000, run_budget - self.spent_tokens)
        cap = min(total_tokens, remaining)
        if estimate_tokens(serialized) > cap:
            note = (
                "result larger than the tool-result budget; use read_email / digest_email for email bodies"
                if cap == total_tokens
                else f"this run has used its tool-result budget ({run_budget:,} tokens); finish with what you have"
            )
            out = preview_text(serialized, cap, note=note)
            self.spent_tokens += estimate_tokens(out)
            return out
        self.spent_tokens += estimate_tokens(serialized)
        return payload

    def read_email(self, message_id: str, offset_chars: int = 0) -> Dict[str, Any]:
        settings = get_settings()
        e = self.emails.get(str(message_id))
        if not e:
            return {"error": f"message {message_id} not in this run's results; run the search first"}
        if self.pages_read >= settings.read_email_pages_per_run:
            return {
                "error": (
                    f"read_email page limit for this run ({settings.read_email_pages_per_run}) reached. Paging cannot "
                    "cover a long body; call digest_email(message_id, question) for anything else you need, or finish."
                )
            }
        self.pages_read += 1
        text = e.get("clean_text") or ""
        cap = chars_for_tokens(settings.recall_max_tokens)
        start = max(0, min(int(offset_chars or 0), len(text)))
        chunk = text[start : start + cap]
        out = {
            "message_id": message_id,
            "subject": e.get("subject"),
            "sender": e.get("sender"),
            "total_chars": len(text),
            "offset_chars": start,
            "content": chunk,
        }
        if start + len(chunk) < len(text):
            out["next_offset_chars"] = start + len(chunk)
            out["note"] = (
                "partial; for a body this large prefer digest_email(message_id, question) instead of paging, "
                "paging everything into your context will not fit"
            )
        return out

    async def digest_email(self, message_id: str, question: str, *, model: str, api_key: str) -> Dict[str, Any]:
        e = self.emails.get(str(message_id))
        if not e:
            return {"error": f"message {message_id} not in this run's results; run the search first"}
        text = e.get("clean_text") or ""
        header = f"Subject: {e.get('subject')}\nFrom: {e.get('sender')}\nDate: {e.get('timestamp')}\n\n"
        return await digest_text(header + text, question, model=model, api_key=api_key, label=f"email {message_id}")


def resolve_body_from(spec: Dict[str, Any], store: Optional[ResultStore]) -> Tuple[Optional[str], Optional[str]]:
    """Return (text, error). spec = {source: 'conversation'|'email', id, start_chars?, end_chars?}."""
    if not isinstance(spec, dict):
        return None, "body_from must be an object"
    source = str(spec.get("source", "")).lower()
    ident = spec.get("id")
    if source == "conversation":
        from ....services.conversation import get_conversation_log

        entries = list(get_conversation_log().iter_entries())
        try:
            idx = int(ident)
        except (TypeError, ValueError):
            return None, "body_from.id must be a conversation entry id (integer)"
        if idx < 0 or idx >= len(entries):
            return None, f"no conversation entry with id {idx}"
        text = entries[idx][2]
    elif source == "email":
        if store is None or str(ident) not in store.emails:
            return None, f"message {ident} is not in this run's search results; search first"
        text = store.emails[str(ident)].get("clean_text") or ""
    else:
        return None, "body_from.source must be 'conversation' or 'email'"
    start = int(spec.get("start_chars") or 0)
    end = spec.get("end_chars")
    text = text[start:int(end)] if end is not None else text[start:]
    if not text.strip():
        return None, "resolved body is empty"
    return text, None


READ_EMAIL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_email",
        "description": (
            "Read the full text of an email returned by an earlier search in this run, one page at a time. "
            "Use for bodies that were shown truncated. For very long bodies prefer digest_email."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "The email's id from the search result."},
                "offset_chars": {
                    "type": "integer",
                    "description": "Character offset to continue from (from next_offset_chars).",
                },
            },
            "required": ["message_id"],
            "additionalProperties": False,
        },
    },
}

DIGEST_EMAIL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "digest_email",
        "description": (
            "Read an entire long email/thread in chunks (separate model calls) and return a compact, faithful "
            "answer to a question about it: a summary, the key terms, a specific figure, each side's position. "
            "Use this instead of paging when a body is too long to read at once. Costs one call per ~12k tokens."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "The email's id from the search result."},
                "question": {
                    "type": "string",
                    "description": (
                        "What you need from the email, e.g. 'summarize the key terms each side is at' "
                        "or 'what liability cap did they propose'."
                    ),
                },
            },
            "required": ["message_id", "question"],
            "additionalProperties": False,
        },
    },
}

__all__ = [
    "ResultStore",
    "resolve_body_from",
    "READ_EMAIL_SCHEMA",
    "DIGEST_EMAIL_SCHEMA",
]
