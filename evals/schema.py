"""Eval case schema, JSON loader and automatic validation checks."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

CATEGORIES = (
    "email_followup",
    "new_task_lookalike",
    "ambiguous_person",
    "clear_person",
    "trigger_management",
    "broad_question_person",
    "multi_person",
    "multi_intent",
)

COPY_RUN_WORDS = 6
MAX_SLOTS = 4  # grading brute-forces the dispatch-to-slot assignment



@dataclass(frozen=True)
class Contact:
    email: str
    display_name: str
    role: str


@dataclass(frozen=True)
class Trigger:
    schedule: str
    payload: str
    status: str


@dataclass(frozen=True)
class AgentDef:
    id: str
    name: str
    description: str
    contacts: tuple[Contact, ...] = ()
    triggers: tuple[Trigger, ...] = ()
    last_user_activity_days_ago: float = 0
    last_run_days_ago: Optional[float] = None


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant", "agent"]
    text: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None


_TARGET_RE = re.compile(r"^(?:create|reuse\((ag_[\w-]+)\))$")


@dataclass(frozen=True)
class Slot:
    """One dispatch a multi-dispatch turn needs, graded on structure (ruling R23).

    ``target`` is ``"create"`` or ``"reuse(<agent_id>)"``. ``must_mention`` holds ``@person:<Full Name>``
    terms only: in case files, on ``create`` slots that start a new person's thread (a reuse id
    already fixes the person and subject; reminder slots carry nothing). ``single_slot`` also puts the
    case's ``expect_person`` on a reuse slot, to mirror ``reuse(id)`` + ``expect_person``; the grader
    ignores an ``@person`` on a reuse slot, as it ignores ``expect_person`` on a reuse (2026-11-07)."""
    target: str
    must_mention: tuple[str, ...] = ()

    @property
    def reuse_id(self) -> Optional[str]:
        m = _TARGET_RE.match(self.target)
        return m.group(1) if m else None

    @property
    def persons(self) -> tuple[str, ...]:
        return tuple(t[len("@person:"):] for t in self.must_mention)


@dataclass(frozen=True)
class Outcome:
    """An acceptable answer. ``dispatch`` outcomes carry ``slots`` and ``ask``; their ``agent_ids``
    are the reuse targets of the slots, in slot order."""
    kind: Literal["reuse", "create", "clarify", "answer_set", "dispatch"]
    agent_ids: tuple[str, ...] = ()
    slots: tuple[Slot, ...] = ()
    ask: bool = False


@dataclass
class Case:
    id: str
    category: str
    split: str
    source: str
    severity: str
    required_agents: list[AgentDef]
    ia_history: list[Turn]
    message: str
    acceptable: list[Outcome]
    expect_person: Optional[str] = None
    clarify_should_name: list[str] = field(default_factory=list)
    unique_facts: dict[str, str] = field(default_factory=dict)
    notes: Optional[str] = None
    original_message: Optional[str] = None  # the pre-paraphrase text, set only on rewritten cases
    context_agents: list[AgentDef] = field(default_factory=list)  # in the roster, not in the labels


# ---------------------------------------------------------------- outcomes

_OUTCOME_RE = re.compile(r"^\s*(reuse|answer_set)\s*\(\s*\[?(.*?)\]?\s*\)\s*$")


def _parse_term(t: Any) -> str:
    if not isinstance(t, str) or not t.strip().startswith("@person:") or not t.strip()[len("@person:"):].strip():
        raise ValueError(f"slot terms are '@person:<Full Name>' only: {t!r}")
    return t.strip()


def _parse_slot(d: Any) -> Slot:
    if not isinstance(d, dict) or not isinstance(d.get("target"), str) or set(d) - {"target", "must_mention"}:
        raise ValueError(f"slot must be {{'target': ..., 'must_mention': [...]}}: {d!r}")
    target = re.sub(r"\s+", "", d["target"])
    if not _TARGET_RE.match(target):
        raise ValueError(f"slot target must be 'create' or 'reuse(<agent_id>)': {d['target']!r}")
    return Slot(target, tuple(_parse_term(t) for t in d.get("must_mention", [])))


def _parse_dispatch(d: dict[str, Any]) -> Outcome:
    if set(d) - {"slots", "ask"} or not isinstance(d.get("slots"), list):
        raise ValueError(f"dispatch outcome must be {{'slots': [...], 'ask': bool}}: {d!r}")
    ask = d.get("ask", False)
    if not isinstance(ask, bool):
        raise ValueError(f"dispatch 'ask' must be a boolean: {ask!r}")
    slots = tuple(_parse_slot(x) for x in d["slots"])
    return Outcome("dispatch", tuple(s.reuse_id for s in slots if s.reuse_id), slots, ask)


def parse_outcome(s: str | dict[str, Any]) -> Outcome:
    """Parse ``reuse(id)``, ``create``, ``clarify``, ``answer_set([ids])`` or a dispatch object."""
    if isinstance(s, dict):
        return _parse_dispatch(s)
    s = s.strip()
    if s in ("create", "clarify"):
        return Outcome(s)  # type: ignore[arg-type]
    m = _OUTCOME_RE.match(s)
    if not m:
        raise ValueError(f"unparseable outcome: {s!r}")
    ids = tuple(p.strip() for p in m.group(2).split(",") if p.strip())
    if not ids:
        raise ValueError(f"outcome has no agent ids: {s!r}")
    if m.group(1) == "reuse" and len(ids) != 1:
        raise ValueError(f"reuse takes exactly one agent id: {s!r}")
    return Outcome(m.group(1), ids)  # type: ignore[arg-type]


def format_outcome(o: Outcome) -> str:
    """A one-line label (dispatch outcomes too); ``outcome_to_json`` gives the case-file form."""
    if o.kind == "reuse":
        return f"reuse({o.agent_ids[0]})"
    if o.kind == "answer_set":
        return f"answer_set([{', '.join(o.agent_ids)}])"
    if o.kind == "dispatch":
        parts = [s.target + (f"[{', '.join(s.persons)}]" if s.persons else "") for s in o.slots]
        return "dispatch(" + "; ".join(parts) + (" + ask" if o.ask else "") + ")"
    return o.kind


def outcome_to_json(o: Outcome) -> str | dict[str, Any]:
    if o.kind != "dispatch":
        return format_outcome(o)
    slots = []
    for s in o.slots:
        slots.append({"target": s.target, "must_mention": list(s.must_mention)})
    return {"slots": slots, "ask": o.ask}


def single_slot(o: Outcome, expect_person: Optional[str]) -> Outcome:
    """The one-slot dispatch equivalent of a ``reuse(id)`` / ``create`` outcome with ``expect_person``."""
    if o.kind not in ("reuse", "create"):
        raise ValueError(f"only reuse/create have a one-slot equivalent, not {o.kind}")
    target = f"reuse({o.agent_ids[0]})" if o.kind == "reuse" else "create"
    terms = (f"@person:{expect_person}",) if expect_person else ()
    return Outcome("dispatch", o.agent_ids, (Slot(target, terms),), False)


# ----------------------------------------------------------- (de)serialise

def _agent_from_dict(d: dict[str, Any]) -> AgentDef:
    return AgentDef(
        id=d["id"],
        name=d["name"],
        description=d["description"],
        contacts=tuple(Contact(c["email"], c["display_name"], c["role"]) for c in d.get("contacts", [])),
        triggers=tuple(Trigger(t["schedule"], t["payload"], t["status"]) for t in d.get("triggers", [])),
        last_user_activity_days_ago=d["last_user_activity_days_ago"],
        last_run_days_ago=d.get("last_run_days_ago"),
    )


def _agent_to_dict(a: AgentDef) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": a.id,
        "name": a.name,
        "description": a.description,
        "contacts": [
            {"email": c.email, "display_name": c.display_name, "role": c.role} for c in a.contacts
        ],
    }
    if a.triggers:
        d["triggers"] = [
            {"schedule": t.schedule, "payload": t.payload, "status": t.status} for t in a.triggers
        ]
    d["last_user_activity_days_ago"] = a.last_user_activity_days_ago
    if a.last_run_days_ago is not None:
        d["last_run_days_ago"] = a.last_run_days_ago
    return d


def _turn_to_dict(t: Turn) -> dict[str, Any]:
    d: dict[str, Any] = {"role": t.role, "text": t.text}
    if t.agent_id is not None:
        d["agent_id"] = t.agent_id
    if t.agent_name is not None:
        d["agent_name"] = t.agent_name
    return d


def case_from_dict(d: dict[str, Any]) -> Case:
    return Case(
        id=d["id"],
        category=d["category"],
        split=d["split"],
        source=d["source"],
        severity=d["severity"],
        required_agents=[_agent_from_dict(a) for a in d["required_agents"]],
        ia_history=[
            Turn(t["role"], t["text"], t.get("agent_id"), t.get("agent_name"))
            for t in d.get("ia_history", [])
        ],
        message=d["message"],
        acceptable=[parse_outcome(s) for s in d["acceptable"]],
        expect_person=d.get("expect_person"),
        clarify_should_name=list(d.get("clarify_should_name", [])),
        unique_facts=dict(d.get("unique_facts", {})),
        notes=d.get("notes"),
        original_message=d.get("original_message"),
        context_agents=[_agent_from_dict(a) for a in d.get("context_agents", [])],
    )


def case_to_dict(case: Case) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": case.id,
        "category": case.category,
        "split": case.split,
        "source": case.source,
        "severity": case.severity,
        "required_agents": [_agent_to_dict(a) for a in case.required_agents],
        "message": case.message,
        "ia_history": [_turn_to_dict(t) for t in case.ia_history],
        "acceptable": [outcome_to_json(o) for o in case.acceptable],
    }
    if case.expect_person is not None:
        d["expect_person"] = case.expect_person
    if case.clarify_should_name:
        d["clarify_should_name"] = list(case.clarify_should_name)
    if case.unique_facts:
        d["unique_facts"] = dict(case.unique_facts)
    if case.notes is not None:
        d["notes"] = case.notes
    if case.original_message is not None:
        d["original_message"] = case.original_message
    if case.context_agents:
        d["context_agents"] = [_agent_to_dict(a) for a in case.context_agents]
    return d


def save_case(case: Case, path: Path) -> None:
    Path(path).write_text(json.dumps(case_to_dict(case), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_cases(path: Path) -> list[Case]:
    """Load every case ``*.json`` file in a directory (sorted by filename; MANIFEST.json is skipped)."""
    return [
        case_from_dict(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(Path(path).glob("*.json"))
        if p.name != "MANIFEST.json"
    ]


# -------------------------------------------------------------- validation

def _words(s: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", s.lower()).split()


def _has_copied_run(message: str, description: str, n: int = COPY_RUN_WORDS) -> Optional[str]:
    m, d = _words(message), _words(description)
    if len(m) < n or len(d) < n:
        return None
    grams = {tuple(d[i : i + n]) for i in range(len(d) - n + 1)}
    for i in range(len(m) - n + 1):
        if tuple(m[i : i + n]) in grams:
            return " ".join(m[i : i + n])
    return None


def _colliding_contacts(case: Case, firsts: Optional[set[str]] = None) -> list[Contact]:
    """Contacts of the required agents that share a first name with another address (optionally
    only for the given lowercased first names)."""
    by_first: dict[str, dict[str, Contact]] = {}
    for a in case.required_agents:
        for c in a.contacts:
            toks = c.display_name.split()
            if not toks:
                continue
            if firsts is None or toks[0].lower() in firsts:
                by_first.setdefault(toks[0].lower(), {})[c.email.lower()] = c
    return [c for emails in by_first.values() if len(emails) >= 2 for c in emails.values()]


def _surname_problems(case: Case, colliding: list[Contact]) -> list[str]:
    problems = []
    msg = case.message.lower()
    for ct in colliding:
        surname = ct.display_name.split()[-1].lower()
        if len(ct.display_name.split()) > 1 and re.search(rf"(?<!\w){re.escape(surname)}(?!\w)", msg):
            problems.append(f"{case.id}: message contains surname of colliding contact {ct.display_name}")
        if ct.email.lower() in msg:
            problems.append(f"{case.id}: message contains email of colliding contact {ct.email}")
    return problems


def _dispatch_problems(case: Case, required: dict[str, AgentDef]) -> list[str]:
    problems = []
    people = {c.display_name.lower() for a in case.required_agents for c in a.contacts}
    for o in case.acceptable:
        if o.kind != "dispatch":
            continue
        if not o.slots:
            problems.append(f"{case.id}: dispatch outcome has no slots")
        if len(o.slots) > MAX_SLOTS:
            problems.append(f"{case.id}: dispatch outcome has {len(o.slots)} slots (max {MAX_SLOTS})")
        reused = [s.reuse_id for s in o.slots if s.reuse_id]
        if len(reused) != len(set(reused)):
            problems.append(f"{case.id}: two slots reuse the same agent")
        for s in o.slots:
            for name in s.persons:
                if name.lower() not in people:
                    problems.append(f"{case.id}: @person:{name} is not a contact of the case's required agents")
            if s.reuse_id and s.persons and case.category in ("multi_person", "multi_intent"):
                problems.append(f"{case.id}: reuse slot {s.target} names a person (R23: create slots only)")
            if len(s.persons) > 1:
                problems.append(f"{case.id}: slot {s.target} names more than one person")
    return problems


def _context_problems(c: Case, required: dict[str, AgentDef],
                      defs: dict[str, tuple[AgentDef, str]]) -> list[str]:
    problems: list[str] = []
    agent_turn_ids = {t.agent_id for t in c.ia_history if t.role == "agent"}
    seen: set[str] = set()
    for a in c.context_agents:
        pre = f"{c.id}: context agent {a.id}"
        if a.id in seen:
            problems.append(f"{pre} is listed twice (duplicate)")
            continue
        seen.add(a.id)
        if a.id not in agent_turn_ids:
            problems.append(f"{pre} is not referenced by an agent turn in ia_history")
        if a.id in required:
            problems.append(f"{pre} is also in required_agents")
        if any(a.id in o.agent_ids for o in c.acceptable):
            problems.append(f"{pre} is an outcome agent_ids target")
        if any(s.reuse_id == a.id for o in c.acceptable for s in o.slots):
            problems.append(f"{pre} is a dispatch slot reuse target")
        if a.id in c.unique_facts:
            problems.append(f"{pre} is a unique_facts key")
        if a.id in defs:
            prev, prev_case = defs[a.id]
            if prev != a:
                problems.append(f"{c.id}: agent {a.id} is defined differently than in {prev_case}")
        else:
            defs[a.id] = (a, c.id)
    return problems


def validate_cases(cases: list[Case]) -> list[str]:
    problems: list[str] = []

    seen_ids: set[str] = set()
    for c in cases:
        if c.id in seen_ids:
            problems.append(f"{c.id}: duplicate case id")
        seen_ids.add(c.id)

    defs: dict[str, tuple[AgentDef, str]] = {}
    for c in cases:
        if c.category not in CATEGORIES:
            problems.append(f"{c.id}: unknown category {c.category!r}")
        required = {a.id: a for a in c.required_agents}

        for a in c.required_agents:
            if a.id in defs:
                prev, prev_case = defs[a.id]
                if prev != a:
                    problems.append(
                        f"{c.id}: agent {a.id} is defined differently than in {prev_case}"
                    )
            else:
                defs[a.id] = (a, c.id)

        problems += _context_problems(c, required, defs)

        for o in c.acceptable:
            for aid in o.agent_ids:
                if aid not in required:
                    problems.append(f"{c.id}: {o.kind} references {aid}, not in required_agents")
        problems += _dispatch_problems(c, required)

        if c.category == "ambiguous_person":
            exempt = (
                len(c.acceptable) == 1
                and c.acceptable[0].kind == "create"
                and c.expect_person is not None
            )
            if not exempt:
                problems += _surname_problems(c, _colliding_contacts(c))
        elif c.category == "multi_person" and any(o.kind == "dispatch" and o.ask for o in c.acceptable):
            # Partial ambiguity: only the person left ambiguous (the clarify_should_name first name)
            # must not be given away; the other person is named in full on purpose.
            firsts = {n.split()[0].lower() for n in c.clarify_should_name if n.split()}
            problems += _surname_problems(c, _colliding_contacts(c, firsts))

        for aid, fact in c.unique_facts.items():
            if aid not in required:
                problems.append(f"{c.id}: unique_facts key {aid} not in required_agents")
                continue
            f = fact.lower()
            if f not in required[aid].description.lower():
                problems.append(f"{c.id}: unique fact {fact!r} not in description of {aid}")
            for oid, other in required.items():
                if oid != aid and f in other.description.lower():
                    problems.append(f"{c.id}: unique fact {fact!r} of {aid} also appears in {oid}")

        for a in c.required_agents:
            run = _has_copied_run(c.message, a.description)
            if run:
                problems.append(
                    f"{c.id}: message wording copied from description of {a.id}: {run!r}"
                )

    return problems
