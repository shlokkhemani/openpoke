"""Keyword search over roster records (problems-and-solutions §3b)."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import List, Literal, Optional, Sequence

from .roster import AgentRecord, get_agent_roster

StatusFilter = Literal["active", "closed", "all"]

_TOKEN = re.compile(r"[a-z0-9@._'-]+")
_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "or", "in", "on", "at", "is", "it", "me", "my",
    "i", "you", "can", "please", "remind", "reminder", "reminders", "that", "this", "one", "be",
    "with", "do", "set", "up", "about", "what", "have", "make", "so", "just",
}

ACTIVE_BOOST = 1.5
ENTITY_MATCH_BONUS = 5.0
_K1 = 1.2
_B = 0.75


def _tokens(text: str) -> List[str]:
    return [tok.strip(".'-") for tok in _TOKEN.findall(text.lower()) if tok.strip(".'-") not in _STOPWORDS]


def _document(record: AgentRecord) -> List[str]:
    return _tokens(" ".join([record.name, record.summary, " ".join(record.entities)]))


def _matches_status(record: AgentRecord, status: StatusFilter) -> bool:
    if status == "active":
        return not record.is_closed
    if status == "closed":
        return record.is_closed
    return True


def find_agents(
    query: Optional[str] = None,
    status: StatusFilter = "all",
    limit: int = 3,
    offset: int = 0,
    records: Optional[Sequence[AgentRecord]] = None,
) -> List[AgentRecord]:
    """Return agents ranked by relevance to `query` (or by recency when no query is given)."""

    pool = [r for r in (records if records is not None else get_agent_roster().records()) if _matches_status(r, status)]
    limit = max(1, min(int(limit or 3), 50))
    offset = max(0, int(offset or 0))

    query_tokens = _tokens(query or "")
    if not query_tokens:
        ranked = sorted(pool, key=lambda r: r.last_active, reverse=True)
        return ranked[offset : offset + limit]

    docs = {r.name: _document(r) for r in pool}
    n_docs = max(len(pool), 1)
    avg_len = (sum(len(d) for d in docs.values()) / n_docs) or 1.0
    doc_freq: Counter[str] = Counter()
    for doc in docs.values():
        doc_freq.update(set(doc))

    query_lower = (query or "").lower()
    scored = []
    for record in pool:
        doc = docs[record.name]
        counts = Counter(doc)
        score = 0.0
        for tok in set(query_tokens):
            tf = counts.get(tok, 0)
            if not tf:
                continue
            idf = math.log(1 + (n_docs - doc_freq[tok] + 0.5) / (doc_freq[tok] + 0.5))
            score += idf * tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * len(doc) / avg_len))
        if any(entity and entity.lower() in query_lower for entity in record.entities):
            score += ENTITY_MATCH_BONUS
        if score > 0 and not record.is_closed:
            score *= ACTIVE_BOOST
        scored.append((score, record.last_active, record))

    # Only agents that actually match the query; no padding with unrelated recent agents.
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [record for _, _, record in scored][offset : offset + limit]


def render_agent(record: AgentRecord) -> str:
    """Render a record for prompts and tool results."""
    from html import escape

    status = "archived" if record.archived else record.status
    summary = escape(record.summary or "(no summary yet)", quote=False)
    # The name stays exactly as stored: Poke copies it into `delegate`, and an escaped name
    # (e.g. "&" -> "&amp;") would not match the existing agent and would create a new one.
    return f'<agent name="{record.name}" status="{status}" last_active="{record.last_active}">{summary}</agent>'


__all__ = ["find_agents", "render_agent", "StatusFilter"]
