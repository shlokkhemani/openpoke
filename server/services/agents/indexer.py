"""One indexer for every search-index refresh path: text always, embeddings once an embedder is ready."""

from __future__ import annotations

import threading
from typing import List, Optional

from ...config import get_settings
from ...logging_config import logger
from ..triggers import get_trigger_service
from .embeddings import Embedder, FastEmbedder
from .index import refresh_search_index
from .store import AgentStore, get_agent_store

_lock = threading.Lock()
_embedder: Optional[Embedder] = None
_dim: Optional[int] = None


def _make_embedder() -> Embedder:
    return FastEmbedder(get_settings().embedding_model)


def ready_embedder() -> Optional[Embedder]:
    """The warmed-up embedder, or None. Never loads anything."""
    return _embedder


def warm_up(embedder: Optional[Embedder] = None) -> Optional[int]:
    """Blocking: embed once (learns the dim, forces the model load), then publish. None on failure."""
    global _embedder, _dim
    try:
        if embedder is None:
            if not get_settings().embedding_model:
                return None  # BM25 only
            embedder = _make_embedder()
        dim = int(embedder.embed(["warm up"]).shape[1])
    except Exception as exc:
        logger.warning(f"embedder warm-up failed, BM25 only: {exc}")
        return None
    with _lock:
        _embedder, _dim = embedder, dim
    return dim


def index_agent(agent_id: str, triggers: Optional[List] = None) -> None:
    """Rebuild the agent's search text, and its embedding when an embedder is ready."""
    if triggers is None:
        triggers = get_trigger_service().list_for_agent(agent_id)
    refresh_search_index(get_agent_store(), agent_id, triggers, ready_embedder())


def backfill_embeddings(store: Optional[AgentStore] = None) -> int:
    """Re-index agents whose embedding is missing or the wrong size. 0 when not warmed up."""
    embedder, dim = _embedder, _dim
    if embedder is None or dim is None:
        return 0
    store = store if store is not None else get_agent_store()
    count = 0
    for agent_id in store.ids_needing_embedding(dim):
        try:
            refresh_search_index(store, agent_id, get_trigger_service().list_for_agent(agent_id), embedder)
            count += 1
        except Exception as exc:
            logger.warning(f"[{agent_id}] embedding backfill failed: {exc}")
    return count


def warm_and_backfill() -> None:
    """Startup job (worker thread); never raises."""
    try:
        if warm_up() is not None:
            n = backfill_embeddings()
            logger.info(f"embedder ready; backfilled {n} agents")
    except Exception as exc:
        logger.warning(f"warm-up and backfill failed: {exc}")


__all__ = ["backfill_embeddings", "index_agent", "ready_embedder", "warm_and_backfill", "warm_up"]
