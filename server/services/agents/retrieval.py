"""Hybrid agent retrieval: BM25 + embeddings fused with RRF (on the message and on history plus message), plus agents referenced by id."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .embeddings import Embedder
from .store import AgentStore


@dataclass(frozen=True)
class RetrievalConfig:
    # Fixed, not tuned. See the comment on the matching Settings fields for the reasoning.
    k: int = 20
    rrf_k: int = 60
    history_turns: int = 2

    @classmethod
    def from_settings(cls, settings: Any) -> "RetrievalConfig":
        return cls(
            k=settings.retrieval_k,
            rrf_k=settings.retrieval_rrf_k,
            history_turns=settings.retrieval_history_turns,
        )


@dataclass
class Candidate:
    agent_id: str
    score: float
    reasons: List[str] = field(default_factory=list)


_AGENT_ID_RE = re.compile(r"\bag_[a-z0-9_]+")


def build_query(message: str, history: Sequence[Tuple[str, ...]], turns: int) -> str:
    """Last ``turns`` history items (oldest first) then the message; items are (role, text[, agent_id])."""
    parts: List[str] = []
    for item in (list(history)[-turns:] if turns > 0 else []):
        text = item[1]
        agent_id = item[2] if len(item) > 2 else None
        parts.append(f"{agent_id} {text}" if agent_id else text)
    parts.append(message)
    return "\n".join(parts)


_TAG_ROLES = {"user_message": "user", "poke_reply": "assistant", "agent_message": "agent"}
# One agent report as ExecutionBatchManager formats it: "[SUCCESS] Name (agent_id=ag_x): text"
_AGENT_ENTRY_RE = re.compile(r"\A\[(?:SUCCESS|FAILED)\] .*? \(agent_id=(ag_[a-z0-9_]+)\): (.*)\Z", re.DOTALL)
_AGENT_ID_IN_ENTRY_RE = re.compile(r"^\[(?:SUCCESS|FAILED)\] .*? \(agent_id=(ag_[a-z0-9_]+)\):", re.MULTILINE)


def history_from_log(entries: Iterable[Tuple[str, str, str]]) -> List[Tuple[str, str, Optional[str]]]:
    """Conversation-log entries ``(tag, timestamp, payload)`` as ``(role, text, agent_id)`` history.

    ``wait`` markers are dropped. A single agent report is reduced to its text and agent id (the shape
    the eval history has); a payload with several reports keeps its whole text and the first id.
    """
    history: List[Tuple[str, str, Optional[str]]] = []
    for tag, _timestamp, payload in entries:
        role = _TAG_ROLES.get(tag)
        if role is None:
            continue
        agent_id: Optional[str] = None
        text = payload
        if role == "agent":
            ids = _AGENT_ID_IN_ENTRY_RE.findall(payload)
            if ids:
                agent_id = ids[0]
            if len(ids) == 1:
                match = _AGENT_ENTRY_RE.match(payload)
                if match:
                    text = match.group(2)
        history.append((role, text, agent_id))
    return history


def _rrf_scores(rankings: Sequence[Sequence[str]], k: int) -> Dict[str, float]:
    scores: Dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, agent_id in enumerate(ranking, start=1):
            scores[agent_id] += 1.0 / (k + rank)
    return scores


def rrf(rankings: List[List[str]], k: int) -> List[str]:
    scores = _rrf_scores(rankings, k)
    return sorted(scores, key=lambda a: (-scores[a], a))


def _bm25_ranking(store: AgentStore, text: str, agents: set, m: int, reasons: Dict[str, List[str]]) -> List[str]:
    ranking = [a for a, _ in store.fts_search(text, len(agents)) if a in agents]
    for a in ranking[:m]:
        if "bm25" not in reasons[a]:
            reasons[a].append("bm25")
    return ranking


def _embedding_ranking(
    store: AgentStore,
    embedder: Optional[Embedder],
    text: str,
    agents: set,
    m: int,
    reasons: Dict[str, List[str]],
) -> List[str]:
    if embedder is None or not text.strip():
        return []
    qv = np.asarray(embedder.embed([text])[0], dtype=np.float32)
    emb_ids, mat = store.embeddings(qv.shape[0])
    if not (emb_ids and qv.any()):
        return []
    sims = mat @ qv
    order = sorted(range(len(emb_ids)), key=lambda i: (-float(sims[i]), emb_ids[i]))
    ordered_ids = [i for i in order if emb_ids[i] in agents]
    for i in ordered_ids[:m]:
        if sims[i] > 0 and "embedding" not in reasons[emb_ids[i]]:
            reasons[emb_ids[i]].append("embedding")
    return [emb_ids[i] for i in ordered_ids]


def search_agents(
    store: AgentStore,
    embedder: Optional[Embedder],
    query: str,
    k: int,
    cfg: RetrievalConfig,
    *,
    message: Optional[str] = None,
) -> List[Candidate]:
    """Top ``k`` agents by BM25 + embedding RRF, then referenced agent ids (always kept, uncapped).

    Without ``message`` the rankings run on ``query``. With a ``message`` different from ``query``
    (history plus message) they also run on the message alone, so history words cannot drown it.
    """
    agents = {a.id for a in store.list_agents()}
    if not agents:
        return []

    reasons: Dict[str, List[str]] = defaultdict(list)
    m = max(1, k)
    texts = [query] if message is None or message == query else [message, query]
    rankings: List[List[str]] = []
    for text in texts:
        for ranking in (
            _bm25_ranking(store, text, agents, m, reasons),
            _embedding_ranking(store, embedder, text, agents, m, reasons),
        ):
            if ranking:
                rankings.append(ranking)

    scores: Dict[str, float] = {a: 0.0 for a in agents}
    for agent_id, s in _rrf_scores(rankings, cfg.rrf_k).items():
        scores[agent_id] += s

    ordered: List[str] = sorted(agents, key=lambda a: (-scores[a], a))[:m]
    for ref in _AGENT_ID_RE.findall(query):
        if ref in agents:
            if "referenced" not in reasons[ref]:
                reasons[ref].append("referenced")
            if ref not in ordered:
                ordered.append(ref)

    return [Candidate(a, scores[a], reasons[a]) for a in ordered]


__all__ = ["Candidate", "RetrievalConfig", "build_query", "history_from_log", "rrf", "search_agents"]
