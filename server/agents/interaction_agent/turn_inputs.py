"""Everything that depends on the roster mode for one IA turn: prompt, roster block, tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ...services.agents.embeddings import Embedder
from ...services.agents.retrieval import RetrievalConfig, build_query
from ...services.agents.store import AgentStore
from ...services.triggers.models import TriggerRecord
from .agent import build_system_prompt
from .roster_view import hybrid_roster_block, render_cards, retrieve_cards
from .tools import HYBRID_TOOL_SCHEMAS, TOOL_SCHEMAS


@dataclass(frozen=True)
class TurnInputs:
    system_prompt: str
    roster_block: str
    tool_schemas: List[Dict[str, Any]]
    search_tool: bool  # whether the turn may call ``search_agents``


def build_turn_inputs(
    mode: str,
    store: AgentStore,
    embedder: Optional[Embedder],
    message: str,
    history: Sequence[Tuple[str, ...]],
    *,
    triggers_for: Callable[[str], List[TriggerRecord]],
    cfg: RetrievalConfig,
) -> TurnInputs:
    """Inputs for one turn in a production roster mode (``full`` or ``hybrid``).

    ``history`` is ``(role, text, agent_id)`` items, oldest first, without the current message.
    """
    if mode == "full":
        cards = render_cards(store, [a.id for a in store.list_agents()], triggers_for)
        return TurnInputs(build_system_prompt("ids"), cards, TOOL_SCHEMAS, False)
    if mode == "hybrid":
        query = build_query(message, history, cfg.history_turns)
        n_total, _ids, cards = retrieve_cards(store, embedder, query, cfg, triggers_for, message=message)
        return TurnInputs(
            build_system_prompt("hybrid"),
            hybrid_roster_block(n_total, cfg.k, cards),
            HYBRID_TOOL_SCHEMAS,
            True,
        )
    raise ValueError(f"unknown roster mode {mode!r}: production modes are 'full' and 'hybrid'")
