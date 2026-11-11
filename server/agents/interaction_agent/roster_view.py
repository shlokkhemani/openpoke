"""How agents are shown to the Interaction Agent, and the legacy (names) tool schemas."""

from __future__ import annotations

import copy
from html import escape
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ...logging_config import logger
from ...services.agents.embeddings import Embedder
from ...services.agents.retrieval import RetrievalConfig, search_agents
from ...services.agents.search_text import describe_schedule
from ...services.agents.store import AgentRecord, AgentStore, ContactRecord
from ...services.triggers.models import TriggerRecord

# The IA's tools as they were before agent ids (dbb79c8): ``send_message_to_agent(agent_name,
# instructions)``. Used only by the eval modes that dispatch by name (``legacy``, ``legacy_rules``).
_LEGACY_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "send_message_to_agent",
            "description": "Deliver instructions to a specific execution agent. Creates a new agent if the name doesn't exist in the roster, or reuses an existing one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Human-readable agent name describing its purpose (e.g., 'Vercel Job Offer', 'Email to Sharanjeet'). This name will be used to identify and potentially reuse the agent."
                    },
                    "instructions": {"type": "string", "description": "Instructions for the agent to execute."},
                },
                "required": ["agent_name", "instructions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message_to_user",
            "description": "Deliver a natural-language response directly to the user. Use this for updates, confirmations, or any assistant response the user should see immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Plain-text message that will be shown to the user and recorded in the conversation log.",
                    },
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_draft",
            "description": "Record an email draft so the user can review the exact text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email for the draft.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject for the draft.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body content (plain text).",
                    },
                },
                "required": ["to", "subject", "body"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait silently when a message is already in conversation history to avoid duplicating responses. Adds a <wait> log entry that is not visible to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of why waiting (e.g., 'Message already sent', 'Draft already created').",
                    },
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]


def legacy_tool_schemas() -> List[Dict[str, Any]]:
    """The pre-id tool schemas (``agent_name``), as a fresh copy."""
    return copy.deepcopy(_LEGACY_TOOL_SCHEMAS)


def _attr(value: str) -> str:
    return escape(value, quote=True)


def _schedule(trigger: TriggerRecord) -> str:
    if trigger.recurrence_rule:
        return describe_schedule(trigger.recurrence_rule, trigger.start_time)
    return f"once at {trigger.start_time}" if trigger.start_time else "once"


def render_candidate(
    agent: AgentRecord, contacts: List[ContactRecord], triggers: List[TriggerRecord]
) -> str:
    """One agent as the IA sees it: id, name, last active date, description, contacts, triggers.

    ``last_active`` is the date of the last user-initiated run, or of creation if there was none.
    Only active triggers are listed. Empty lines are left out.
    """
    last_active = (agent.last_user_activity_at or agent.created_at).date().isoformat()
    lines = [
        f'<agent id="{_attr(agent.id)}" name="{_attr(agent.name or "agent")}" last_active="{last_active}">'
    ]
    if agent.description:
        lines.append(f"description: {agent.description}")
    if contacts:
        people = ", ".join(
            f"{c.display_name} <{c.email}>" if c.display_name else f"<{c.email}>" for c in contacts
        )
        lines.append(f"contacts: {people}")
    for t in triggers:
        if t.status == "active":
            lines.append(f"trigger: {_schedule(t)}: {t.payload} ({t.status})")
    lines.append("</agent>")
    return "\n".join(lines)


def render_cards(
    store: AgentStore, ids: Sequence[str], triggers_for: Callable[[str], List[TriggerRecord]]
) -> str:
    """The given agents as cards, in order; ids missing from the store are skipped. "None" if empty."""
    cards: List[str] = []
    for agent_id in ids:
        agent = store.get(agent_id)
        if agent is not None:
            cards.append(render_candidate(agent, store.contacts_for(agent_id), triggers_for(agent_id)))
    return "\n".join(cards) if cards else "None"


def retrieve_cards(
    store: AgentStore,
    embedder: Optional[Embedder],
    query: str,
    cfg: RetrievalConfig,
    triggers_for: Callable[[str], List[TriggerRecord]],
    *,
    message: Optional[str] = None,
) -> Tuple[int, List[str], str]:
    """``(n_total, ids, cards)`` for the top ``cfg.k`` agents; BM25 only if the embedding call fails."""
    n_total = len(store.list_agents())
    try:
        found = search_agents(store, embedder, query, cfg.k, cfg, message=message)
    except Exception as exc:
        if embedder is None:
            raise
        logger.warning(f"embedding search failed, retrying with BM25 only: {exc}")
        found = search_agents(store, None, query, cfg.k, cfg, message=message)
    ids = [c.agent_id for c in found]
    return n_total, ids, render_cards(store, ids, triggers_for)


def hybrid_roster_block(n: int, k: int, cards: str) -> str:
    """The ``<active_agents>`` body for ``hybrid``: a header saying how partial the list is, then cards."""
    if n <= 0:
        return "None"
    if n <= k:
        header = f"All {n} agents are shown."
    else:
        header = (
            f"These are the {k} agents most relevant to this message, of {n}. "
            "If none fits, call `search_agents` before creating a new agent."
        )
    return f"{header}\n{cards}"


__all__ = ["hybrid_roster_block", "legacy_tool_schemas", "render_candidate", "render_cards", "retrieve_cards"]
