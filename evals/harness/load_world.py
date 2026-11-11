"""Load a roster into a temporary ``AgentStore`` the way production builds one, for the retrieval eval.

``CachedEmbedder`` memoises text -> vector so every store and query shares one embedding per distinct text.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Iterable, Optional

import numpy as np

from evals.harness.full_roster import _agent_record, _trigger_records
from evals.schema import AgentDef
from evals.world.roster import World
from server.services.agents.index import refresh_search_index
from server.services.agents.store import AgentStore, ContactRecord


class CachedEmbedder:
    """Wraps an embedder; each distinct text is embedded once (misses go to the inner embedder in one batch)."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self._cache: dict[str, np.ndarray] = {}

    def embed(self, texts: list[str]) -> np.ndarray:
        texts = list(texts)
        misses = list(dict.fromkeys(t for t in texts if t not in self._cache))
        if misses:
            for text, vec in zip(misses, self.inner.embed(misses)):
                self._cache[text] = np.asarray(vec, dtype=np.float32)
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return np.stack([self._cache[t] for t in texts])


def load_into_store(roster: Iterable[AgentDef], world: World, store: AgentStore, embedder,
                    descriptions: Optional[dict[str, str]] = None, *, keep_order: bool = False) -> None:
    """Insert ``roster`` (agents, contacts, search text, embeddings); search text holds active triggers only.

    ``keep_order`` gives the k-th agent a creation time k seconds after the clock, so ``store.list_agents()``
    returns the roster in roster order (otherwise all tie and the store orders by id).

    No uses and no logs: retrieval ignores them. ``world`` is kept for symmetry with the other loaders.
    """
    descriptions = descriptions or {}
    for k, a in enumerate(roster):
        record = _agent_record(a, descriptions)
        if keep_order:
            record = replace(record, created_at=record.created_at + timedelta(seconds=k))
        store.insert_agent(record)
        store.add_contacts(a.id, [ContactRecord(c.email, c.display_name, c.role) for c in a.contacts])
        triggers = _trigger_records(a)
        refresh_search_index(store, a.id, triggers, embedder)


__all__ = ["CachedEmbedder", "load_into_store"]
