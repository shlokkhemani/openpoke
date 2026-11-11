"""The ``full`` roster: every roster agent as the production agent card (``render_candidate``)."""
from __future__ import annotations

from typing import Iterable

from evals.clock import EVAL_NOW, days_ago
from evals.schema import AgentDef
from server.agents.interaction_agent.roster_view import render_candidate
from server.services.agents.store import AgentRecord, ContactRecord
from server.services.triggers.models import TriggerRecord

_CLOCK = EVAL_NOW.isoformat()


def _agent_record(a: AgentDef, descriptions: dict[str, str]) -> AgentRecord:
    # AgentDef has no creation time: EVAL_NOW stands in (as in regen_descriptions).
    last = a.last_user_activity_days_ago
    return AgentRecord(
        id=a.id,
        name=a.name,
        description=descriptions.get(a.id, a.description),
        created_at=EVAL_NOW,
        last_user_activity_at=days_ago(last) if last is not None else None,
        last_run_at=days_ago(a.last_run_days_ago) if a.last_run_days_ago is not None else None,
    )


def _trigger_records(a: AgentDef) -> list[TriggerRecord]:
    return [
        TriggerRecord(id=i, agent_id=a.id, payload=t.payload, recurrence_rule=t.schedule, status=t.status,
                      created_at=_CLOCK, updated_at=_CLOCK)
        for i, t in enumerate(a.triggers, 1)
    ]


def _card(a: AgentDef, descriptions: dict[str, str]) -> str:
    """``render_candidate``'s card, with the world's schedule text as the trigger's readable text.

    The card is rendered without triggers and the active ones are added in ``render_candidate``'s
    trigger-line format, so a world schedule ("daily at 8am") is shown as written whatever
    ``describe_schedule`` would make of it.
    """
    contacts = [ContactRecord(c.email, c.display_name, c.role) for c in a.contacts]
    lines = render_candidate(_agent_record(a, descriptions), contacts, []).split("\n")
    triggers = [f"trigger: {t.recurrence_rule}: {t.payload} ({t.status})"
                for t in _trigger_records(a) if t.status == "active"]
    return "\n".join(lines[:-1] + triggers + lines[-1:])


def render_full_roster(roster: list[AgentDef], descriptions: dict[str, str]) -> str:
    """Every agent of ``roster`` as a card, in roster order; ``descriptions`` overrides by id."""
    if not roster:
        return "None"
    return "\n".join(_card(a, descriptions) for a in roster)


def description_coverage(agent_ids: Iterable[str], descriptions: dict[str, str]) -> tuple[int, int]:
    """(agents with a description in ``descriptions``, all agents)."""
    ids = list(agent_ids)
    return sum(i in descriptions for i in ids), len(ids)


__all__ = ["description_coverage", "render_full_roster"]
