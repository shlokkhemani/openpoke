"""Token-budgeted worker history for the budgeted context strategy.

Legacy (`ExecutionAgent.build_system_prompt_with_history`) pastes the worker's entire log into
its system prompt on every run. This module is the budgeted alternative: it renders the newest
entries verbatim within a token budget, bounds any oversized entry to a head/tail preview, and
lists older entries as one-line index items with stable ids so the worker can fetch them with the
`recall_worker_history` tool. It never edits the log.

Only used when `settings.budgeted_context` is true.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Dict, List, Optional, Sequence, Tuple

from ....config import get_settings
from ....services.execution import get_execution_agent_logs
from ....utils.tokens import chars_for_tokens, estimate_tokens

_INDEX_SNIPPET_CHARS = 90


@dataclass
class WorkerEntry:
    index: int
    tag: str
    timestamp: str
    payload: str


@dataclass
class BuiltWorkerHistory:
    transcript: str
    inline_entries: int = 0
    truncated_entries: int = 0
    indexed_entries: int = 0
    estimated_tokens: int = 0


def load_entries(agent_name: str) -> List[WorkerEntry]:
    logs = get_execution_agent_logs()
    return [WorkerEntry(index=i, tag=tag, timestamp=ts, payload=payload)
            for i, (tag, ts, payload) in enumerate(logs.iter_entries(agent_name))]


def _preview(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = max(200, int(max_chars * 0.7))
    tail = max(100, max_chars - head)
    omitted = len(text) - head - tail
    return (f"{text[:head]}\n[... {omitted:,} characters omitted; call recall_worker_history with this entry id "
            f"to read the full text ...]\n{text[-tail:]}")


def render_entry(entry: WorkerEntry, *, entry_max_tokens: int) -> Tuple[str, bool]:
    payload = entry.payload
    truncated = False
    max_chars = chars_for_tokens(entry_max_tokens)
    if entry_max_tokens > 0 and len(payload) > max_chars:
        payload = _preview(payload, max_chars)
        truncated = True
    attrs = [f'id="{entry.index}"']
    if entry.timestamp:
        attrs.append(f'timestamp="{entry.timestamp}"')
    if truncated:
        attrs.append(f'truncated="true" total_chars="{len(entry.payload)}"')
    return f"<{entry.tag} {' '.join(attrs)}>{escape(payload, quote=False)}</{entry.tag}>", truncated


def _index_line(entry: WorkerEntry) -> str:
    snippet = " ".join(entry.payload.split())
    if len(snippet) > _INDEX_SNIPPET_CHARS:
        snippet = snippet[:_INDEX_SNIPPET_CHARS] + "…"
    ts = f" {entry.timestamp}" if entry.timestamp else ""
    return f"[{entry.index}]{ts} {entry.tag}: {escape(snippet, quote=False)}"


def build_worker_history(agent_name: str, *, budget_tokens: Optional[int] = None,
                         entry_max_tokens: Optional[int] = None, index_max_lines: Optional[int] = None) -> BuiltWorkerHistory:
    settings = get_settings()
    budget = budget_tokens if budget_tokens is not None else settings.worker_history_budget_tokens
    entry_cap = entry_max_tokens if entry_max_tokens is not None else settings.context_entry_max_tokens
    index_cap = index_max_lines if index_max_lines is not None else settings.context_index_max_lines

    entries = load_entries(agent_name)
    result = BuiltWorkerHistory(transcript="")
    if not entries:
        return result

    inline: List[str] = []
    indexed: List[WorkerEntry] = []
    remaining = budget
    cutoff = False
    for entry in reversed(entries):
        if cutoff:
            indexed.append(entry)
            continue
        xml, was_truncated = render_entry(entry, entry_max_tokens=entry_cap)
        cost = estimate_tokens(xml)
        if cost > remaining and inline:
            cutoff = True
            indexed.append(entry)
            continue
        inline.append(xml)
        remaining -= cost
        result.inline_entries += 1
        result.truncated_entries += int(was_truncated)
    inline.reverse()
    indexed.reverse()

    parts: List[str] = []
    if indexed:
        result.indexed_entries = len(indexed)
        shown = indexed[-index_cap:] if index_cap > 0 else []
        hidden = len(indexed) - len(shown)
        lines = [f'<older_entries count="{len(indexed)}" note="earlier requests handled by this agent, not shown in full; '
                 f'call recall_worker_history with entry ids or a search query if you need one">']
        if hidden:
            lines.append(f"[{indexed[0].index}..{indexed[hidden - 1].index}] {hidden} earlier entries (search with recall_worker_history)")
        lines.extend(_index_line(e) for e in shown)
        lines.append("</older_entries>")
        parts.append("\n".join(lines))
    parts.extend(inline)
    result.transcript = "\n".join(parts)
    result.estimated_tokens = estimate_tokens(result.transcript)
    return result


# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------
_STOPWORDS = {"the", "a", "an", "to", "of", "for", "and", "or", "in", "on", "at", "is", "it", "that", "this", "with",
              "about", "from", "by", "as", "be", "was", "were", "are", "email", "please", "find", "get", "me", "my", "i"}


def _terms(query: str) -> List[str]:
    raw = [t.strip(".,;:!?\"'()[]") for t in query.lower().split()]
    terms = [t for t in raw if len(t) >= 2 and t not in _STOPWORDS]
    return terms or [t for t in raw if t]


def _search(entries: List[WorkerEntry], query: str, limit: int) -> List[WorkerEntry]:
    phrase = query.strip().lower()
    terms = _terms(query)
    if not phrase:
        return []
    scored: List[Tuple[int, int, WorkerEntry]] = []
    for e in entries:
        text = e.payload.lower()
        score = len(terms) + 2 if phrase in text else sum(1 for t in terms if t in text)
        if score > 0:
            scored.append((score, e.index, e))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    # Keep rank order (best match first) so the recall budget is spent on the most relevant entry,
    # not on the oldest one.
    return [e for _, _, e in scored[:limit]]


def recall_worker_entries(agent_name: str, *, entry_ids: Optional[Sequence[int]] = None, query: Optional[str] = None,
                          limit: int = 5, offset_chars: int = 0, max_tokens: Optional[int] = None) -> Dict:
    settings = get_settings()
    cap_chars = chars_for_tokens(max_tokens if max_tokens is not None else settings.recall_max_tokens)
    entries = load_entries(agent_name)
    by_id = {e.index: e for e in entries}
    selected: List[WorkerEntry] = []
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
            out.append({"id": e.index, "tag": e.tag, "timestamp": e.timestamp, "total_chars": total, "content": None,
                        "note": "recall budget exhausted for this call; recall this id on its own if needed"})
            continue
        chunk = text[start:start + room]
        spent += len(chunk)
        item = {"id": e.index, "tag": e.tag, "timestamp": e.timestamp, "total_chars": total, "content": chunk}
        if start + len(chunk) < total:
            item["next_offset_chars"] = start + len(chunk)
            item["note"] = "partial; call again with offset_chars=next_offset_chars for more"
        out.append(item)
    return {"entries": out, "matched": len(selected), "total_entries": len(entries)}


__all__ = ["build_worker_history", "recall_worker_entries", "BuiltWorkerHistory"]
