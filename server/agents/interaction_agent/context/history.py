"""Token-budgeted assembly of the interaction agent's conversation history.

Legacy behaviour pastes the whole history (or the summary plus the entire
unsummarised tail) into every prompt. This module replaces that with:

- a fixed token budget for the history block, filled newest-first so the most
  recent context is always verbatim;
- per-entry bounding: an oversized entry is shown as a head/tail preview with
  its size and id, never in full;
- an index of the older entries that did not fit, one short line each, so the
  agent knows they exist and can fetch them with the recall_history tool;
- stable entry ids (the entry's index in the conversation log) on every line,
  which is what recall_history takes.

The compacted summary, when one exists, is always included inline: it is small
and is the only place older facts survive without a fetch.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Iterable, List, Optional, Sequence, Tuple

from ....config import get_settings
from ....utils.tokens import chars_for_tokens, estimate_tokens
from ....services.conversation.log import get_conversation_log
from ....services.conversation.summarization import get_working_memory_log
from ....services.conversation.summarization.state import LogEntry


@dataclass
class BuiltContext:
    transcript: str
    inline_entries: int = 0
    truncated_entries: int = 0
    indexed_entries: int = 0
    summary_tokens: int = 0
    estimated_tokens: int = 0


_INDEX_SNIPPET_CHARS = 90


def _preview(text: str, max_chars: int) -> str:
    """Head/tail preview of an oversized payload."""
    if len(text) <= max_chars:
        return text
    head = max(200, int(max_chars * 0.7))
    tail = max(100, max_chars - head)
    omitted = len(text) - head - tail
    return (
        f"{text[:head]}\n[... {omitted:,} characters omitted; call recall_history with this entry id "
        f"to read the full text ...]\n{text[-tail:]}"
    )


def render_entry(entry: LogEntry, *, entry_max_tokens: int) -> Tuple[str, bool]:
    """Render one entry as a tagged line. Returns (xml, was_truncated)."""
    payload = entry.payload
    truncated = False
    max_chars = chars_for_tokens(entry_max_tokens)
    if entry_max_tokens > 0 and len(payload) > max_chars:
        payload = _preview(payload, max_chars)
        truncated = True
    safe = escape(payload, quote=False)
    attrs = [f'id="{entry.index}"']
    if entry.timestamp:
        attrs.append(f'timestamp="{entry.timestamp}"')
    if truncated:
        attrs.append(f'truncated="true" total_chars="{len(entry.payload)}"')
    return f"<{entry.tag} {' '.join(attrs)}>{safe}</{entry.tag}>", truncated


def _index_line(entry: LogEntry) -> str:
    snippet = " ".join(entry.payload.split())
    if len(snippet) > _INDEX_SNIPPET_CHARS:
        snippet = snippet[:_INDEX_SNIPPET_CHARS] + "…"
    ts = f" {entry.timestamp}" if entry.timestamp else ""
    return f"[{entry.index}]{ts} {entry.tag}: {escape(snippet, quote=False)}"


def _load_entries() -> Tuple[str, List[LogEntry]]:
    """Return (summary_text, entries_to_consider) honouring the summariser state."""
    settings = get_settings()
    if settings.summarization_enabled:
        state = get_working_memory_log().load_summary_state()
        if state.summary_text.strip() or state.last_index >= 0:
            return state.summary_text, list(state.unsummarized_entries)
    log = get_conversation_log()
    entries = [
        LogEntry(tag=tag, payload=payload, index=i, timestamp=ts or None)
        for i, (tag, ts, payload) in enumerate(log.iter_entries())
    ]
    return "", entries


def build_history(
    *,
    budget_tokens: Optional[int] = None,
    entry_max_tokens: Optional[int] = None,
    index_max_lines: Optional[int] = None,
) -> BuiltContext:
    settings = get_settings()
    budget = budget_tokens if budget_tokens is not None else settings.context_budget_tokens
    entry_cap = entry_max_tokens if entry_max_tokens is not None else settings.context_entry_max_tokens
    index_cap = index_max_lines if index_max_lines is not None else settings.context_index_max_lines

    summary_text, entries = _load_entries()
    result = BuiltContext(transcript="")

    parts: List[str] = []
    remaining = budget

    summary_block = ""
    if summary_text.strip():
        summary_block = f"<conversation_summary>{escape(summary_text.strip(), quote=False)}</conversation_summary>"
        result.summary_tokens = estimate_tokens(summary_block)
        remaining -= result.summary_tokens

    # Fill newest-first so recent turns are always verbatim.
    inline: List[str] = []
    indexed: List[LogEntry] = []
    cutoff_reached = False
    for entry in reversed(entries):
        if cutoff_reached:
            indexed.append(entry)
            continue
        xml, was_truncated = render_entry(entry, entry_max_tokens=entry_cap)
        cost = estimate_tokens(xml)
        if cost > remaining and inline:
            cutoff_reached = True
            indexed.append(entry)
            continue
        inline.append(xml)
        remaining -= cost
        result.inline_entries += 1
        result.truncated_entries += int(was_truncated)
    inline.reverse()
    indexed.reverse()  # chronological

    if summary_block:
        parts.append(summary_block)

    if indexed:
        result.indexed_entries = len(indexed)
        shown = indexed[-index_cap:] if index_cap > 0 else []
        hidden = len(indexed) - len(shown)
        lines = [
            f'<older_entries count="{len(indexed)}" note="not shown inline to save context; '
            f'call recall_history with entry ids or a search query to read any of them in full">'
        ]
        if hidden:
            first, last = indexed[0].index, indexed[hidden - 1].index
            lines.append(f"[{first}..{last}] {hidden} earlier entries (search with recall_history)")
        lines.extend(_index_line(e) for e in shown)
        lines.append("</older_entries>")
        parts.append("\n".join(lines))

    parts.extend(inline)
    result.transcript = "\n".join(parts)
    result.estimated_tokens = estimate_tokens(result.transcript)
    return result


# ---------------------------------------------------------------------------
# Recall support (used by the recall_history tool)
# ---------------------------------------------------------------------------
def _all_entries() -> List[LogEntry]:
    log = get_conversation_log()
    return [
        LogEntry(tag=tag, payload=payload, index=i, timestamp=ts or None)
        for i, (tag, ts, payload) in enumerate(log.iter_entries())
    ]


_STOPWORDS = {
    "the", "a", "an", "to", "of", "for", "and", "or", "in", "on", "at", "is", "it", "that", "this",
    "with", "about", "from", "by", "as", "be", "was", "were", "are", "email", "message", "draft",
    "please", "find", "get", "show", "me", "my", "we", "our", "you", "your", "i",
}


def _terms(query: str) -> List[str]:
    raw = [t.strip(".,;:!?\"'()[]") for t in query.lower().split()]
    terms = [t for t in raw if len(t) >= 2 and t not in _STOPWORDS]
    return terms or [t for t in raw if t]


def _search(entries: List[LogEntry], query: str, limit: int) -> List[LogEntry]:
    """Rank entries by how many query terms they contain, then by recency.

    An exact phrase match scores highest; otherwise entries need at least one term. Rare
    identifiers (draft/thread ids, addresses) naturally dominate because generic words are
    filtered as stopwords.
    """
    phrase = query.strip().lower()
    terms = _terms(query)
    if not phrase:
        return []
    scored: List[Tuple[int, int, LogEntry]] = []
    for e in entries:
        text = e.payload.lower()
        if phrase in text:
            score = len(terms) + 2
        else:
            score = sum(1 for t in terms if t in text)
        if score > 0:
            scored.append((score, e.index, e))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    # Keep rank order (best match first) so the recall budget is spent on the most relevant entry,
    # not on the oldest one.
    return [e for _, _, e in scored[:limit]]


def recall_entries(
    *,
    entry_ids: Optional[Sequence[int]] = None,
    query: Optional[str] = None,
    limit: int = 5,
    offset_chars: int = 0,
    max_tokens: Optional[int] = None,
) -> dict:
    """Return full entries by id, or the most recent entries matching a query."""
    settings = get_settings()
    cap_chars = chars_for_tokens(max_tokens if max_tokens is not None else settings.recall_max_tokens)
    entries = _all_entries()
    by_id = {e.index: e for e in entries}

    selected: List[LogEntry] = []
    if entry_ids:
        for raw in entry_ids:
            try:
                idx = int(raw)
            except (TypeError, ValueError):
                continue
            if idx in by_id:
                selected.append(by_id[idx])
    elif query:
        selected = _search(entries, query, max(1, limit))

    out = []
    spent = 0
    for e in selected:
        text = e.payload
        total = len(text)
        start = max(0, min(offset_chars, total)) if len(selected) == 1 else 0
        room = cap_chars - spent
        if room <= 0:
            out.append({"id": e.index, "tag": e.tag, "timestamp": e.timestamp, "total_chars": total,
                        "content": None, "note": "recall budget exhausted for this call; recall this id on its own if needed"})
            continue
        chunk = text[start:start + room]
        spent += len(chunk)
        item = {"id": e.index, "tag": e.tag, "timestamp": e.timestamp, "total_chars": total, "content": chunk}
        if start + len(chunk) < total:
            item["next_offset_chars"] = start + len(chunk)
            item["note"] = "partial; call again with offset_chars=next_offset_chars for more"
        out.append(item)

    return {
        "entries": out,
        "matched": len(selected),
        "total_entries": len(entries),
    }


__all__ = ["BuiltContext", "build_history", "recall_entries", "render_entry"]
