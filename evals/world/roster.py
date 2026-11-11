"""World data model, (de)serialisation, nested rosters and planted-fact extraction."""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from evals.schema import AgentDef, Case, Contact, _agent_from_dict, _agent_to_dict

# Planted facts in filler descriptions, one code-style kind per topic: ticket #Q-48213,
# invoice INV-20931, confirmation CONF-X7K2QD, order ORD-48213, pull request PR-4821,
# reference REF-20931, thread MSG-20931, reminder RMD-20931, digest DGT-20931, prescription RX-209314.
FACT_RE = re.compile(
    r"#Q-\d{5}|INV-\d{5}|CONF-[A-Z2-7]{6}|ORD-\d{5}|PR-\d{4}|REF-\d{5}|MSG-\d{5}|RMD-\d{5}|DGT-\d{5}|RX-\d{6}")


@dataclass
class World:
    contacts: list[Contact] = field(default_factory=list)
    agents: dict[str, AgentDef] = field(default_factory=dict)
    filler_order: list[str] = field(default_factory=list)
    logs: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    uses: dict[str, list[tuple[float, str]]] = field(default_factory=dict)


def extract_fact(description: str) -> str:
    """The planted unique fact of a filler description, or the whole description if none."""
    m = FACT_RE.search(description)
    return m.group(0) if m else description


def _shuffle_seed(case_id: str, n: int) -> int:
    return int.from_bytes(hashlib.sha256(f"{case_id}|{n}".encode()).digest()[:8], "big")


def roster_for(case: Case, world: World, n: int) -> list[AgentDef]:
    """Required agents, then the case's context agents (skipping ids already present), then the first
    fillers from ``world.filler_order`` not yet in the roster up to ``n``; shuffled by (case.id, n)."""
    required = {a.id: a for a in case.required_agents}
    members = dict(required)
    for a in case.context_agents:
        members.setdefault(a.id, a)
    if n < len(members):
        raise ValueError(f"roster size {n} is smaller than the {len(members)} required and context agents")
    roster = list(members.values())
    for aid in world.filler_order:
        if len(roster) >= n:
            break
        if aid not in members:
            roster.append(world.agents[aid])
    if len(roster) < n:
        raise ValueError(f"world has too few agents for roster size {n}")
    random.Random(_shuffle_seed(case.id, n)).shuffle(roster)
    return roster


def save_world(w: World, path: Path) -> None:
    data = {
        "contacts": [{"email": c.email, "display_name": c.display_name, "role": c.role} for c in w.contacts],
        "agents": {aid: _agent_to_dict(a) for aid, a in w.agents.items()},
        "filler_order": list(w.filler_order),
        "logs": {aid: [[t, p] for t, p in es] for aid, es in w.logs.items()},
        "uses": {aid: [[d, s] for d, s in us] for aid, us in w.uses.items()},
    }
    Path(path).write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_world(path: Path) -> World:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return World(
        contacts=[Contact(c["email"], c["display_name"], c["role"]) for c in d["contacts"]],
        agents={aid: _agent_from_dict(a) for aid, a in d["agents"].items()},
        filler_order=list(d["filler_order"]),
        logs={aid: [(t, p) for t, p in es] for aid, es in d["logs"].items()},
        uses={aid: [(dd, s) for dd, s in us] for aid, us in d["uses"].items()},
    )
