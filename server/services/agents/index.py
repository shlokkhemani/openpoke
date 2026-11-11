"""Rebuild an agent's search indexes (FTS text, optional embedding)."""

from __future__ import annotations

from typing import Any, List, Optional

from ..triggers.models import TriggerRecord
from .search_text import build_search_text
from .store import AgentStore


def refresh_search_index(
    store: AgentStore, agent_id: str, triggers: List[TriggerRecord], embedder: Optional[Any] = None
) -> None:
    """Rebuild the search text; also the embedding when an embedder (``embed(list[str])``) is given."""
    agent = store.get(agent_id)
    if agent is None:
        return
    text = build_search_text(agent, store.contacts_for(agent_id), triggers)
    store.set_search_text(agent_id, text)
    if embedder is not None:
        store.set_embedding(agent_id, embedder.embed([text])[0])


__all__ = ["refresh_search_index"]
