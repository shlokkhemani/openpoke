"""Rewrite an agent's description after each run with one tool-less LLM call."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from ...logging_config import logger
from ..triggers.models import TriggerRecord
from .index import refresh_search_index
from .store import AgentStore, ContactRecord

MAX_SUBJECTS = 10
FALLBACK_CHARS = 300

SYSTEM_PROMPT = (
    "You maintain the one-paragraph description of an assistant agent that handles one ongoing task "
    "or relationship for a user. Rewrite it in 1-3 plain sentences: what this agent is for, and where "
    "things currently stand (who replied and what they said, what is still pending). Keep names, "
    "email addresses and identifiers that would help find this agent later. Reply with the "
    "description only: no preamble, no quotes, no markdown."
)

LLMCall = Callable[..., Awaitable[Dict[str, Any]]]


@dataclass
class RunFacts:
    """What the execution runtime saw during a run."""

    contacts: List[ContactRecord] = field(default_factory=list)
    subjects: List[str] = field(default_factory=list)


def merge_subjects(existing: List[str], new: List[str]) -> List[str]:
    """Deduplicate in order and cap at MAX_SUBJECTS."""
    merged = list(existing)
    for subject in new:
        if subject not in merged:
            merged.append(subject)
    return merged[:MAX_SUBJECTS]


def _contact_line(contact: ContactRecord) -> str:
    return f"{contact.display_name} <{contact.email}>" if contact.display_name else contact.email


class DescriptionUpdater:
    def __init__(
        self,
        store: AgentStore,
        llm: LLMCall,
        model: str,
        triggers: Optional[Callable[[str], List[TriggerRecord]]] = None,
        embedder: Optional[Any] = None,
        index: Optional[Callable[..., None]] = None,
    ) -> None:
        self.store = store
        self.llm = llm
        self.model = model
        self.triggers = triggers
        self.embedder = embedder
        self.index = index

    def _prompt(self, agent_id: str, instructions: str, final_response: str, facts: Optional[RunFacts]) -> str:
        agent = self.store.get(agent_id)
        contacts = facts.contacts if facts else []
        subjects = merge_subjects([], facts.subjects) if facts else []
        return "\n".join([
            f"Previous description: {agent.description if agent and agent.description else '(none)'}",
            f"Latest instructions: {instructions}",
            f"Final response: {final_response}",
            "Contacts: " + ("; ".join(_contact_line(c) for c in contacts) or "(none)"),
            "Email subjects: " + ("; ".join(subjects) or "(none)"),
        ])

    async def update(
        self, agent_id: str, instructions: str, final_response: str, facts: Optional[RunFacts] = None
    ) -> str:
        text, _ = await self.update_checked(agent_id, instructions, final_response, facts)
        return text

    async def update_checked(
        self, agent_id: str, instructions: str, final_response: str, facts: Optional[RunFacts] = None
    ) -> Tuple[str, bool]:
        """Like ``update`` but also says whether the stored text is the fallback: (text, fell_back)."""
        text = ""
        try:
            response = await self.llm(
                model=self.model,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": self._prompt(agent_id, instructions, final_response, facts)}],
            )
            message = (response.get("choices") or [{}])[0].get("message") or {}
            text = (message.get("content") or "").strip()
        except Exception as exc:
            logger.warning(f"[{agent_id}] description update failed, using fallback: {exc}")
        fell_back = not text
        if fell_back:
            existing = self.store.get(agent_id)
            existing_text = ((existing.description if existing else "") or "").strip()
            if existing_text:
                text = existing.description  # keep what we have: one failed call must not erase it
            else:
                text = instructions[:FALLBACK_CHARS]
                self.store.update_description(agent_id, text)
        else:
            self.store.update_description(agent_id, text)
        try:
            triggers = self.triggers(agent_id) if self.triggers else []
            if self.index is not None:
                self.index(agent_id, triggers)
            else:
                refresh_search_index(self.store, agent_id, triggers, self.embedder)
        except Exception as exc:
            logger.warning(f"[{agent_id}] search index refresh failed: {exc}")
        return text, fell_back


__all__ = ["DescriptionUpdater", "RunFacts", "merge_subjects"]
