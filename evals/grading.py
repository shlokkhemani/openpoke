"""Exact-match grading of the IA's recorded tool calls (design §5.3, scope §1a). No LLM judge.

``Grade.outcome_kind`` is the observed behaviour:

- the matched acceptable outcome's kind when the case passed (when a reply matches both ``clarify``
  and a more specific outcome such as ``answer_set``, the specific one);
- otherwise ``"mixed"`` (reused and created), ``"reuse"`` (reused only), ``"create"`` (created only);
- ``"invalid"`` if ``send_message_to_agent`` was called but every call was invalid or ambiguous;
- with no dispatch call at all: ``"answer_set"`` if the user-facing text contains any of the case's
  unique facts, ``"clarify"`` if a user message was sent, else ``"none"``. A user message is a
  ``send_message_to_user`` call or, when the turn sent none, a non-blank final reply: production delivers
  the IA's last assistant text when no message was sent *(amended 2026-11-07 after experiment 5, logged in
  ``evals/results/changes.md``)*.

Decisions not fixed by the brief:

- Invalid ``send_message_to_agent`` calls are flagged (``invalid_call``) and otherwise ignored for
  reuse/create/answer_set (the tool returned an error and did nothing, so the IA may retry), but any
  ``send_message_to_agent`` call, invalid included, rules out ``clarify``.
- ``answer_set`` also requires that nothing was created.
- **``expect_person`` on a reuse** *(amended 2026-11-07 after experiment 1, logged in
  ``evals/results/changes.md``)*: it does not affect pass/fail. The reused agent already holds the
  thread and the address, so first-name-only instructions to the right agent are correct. A
  ``create`` with ``expect_person`` still needs the full name or an email of that person (a wrong
  person is a real risk there). ``person_ok`` is still computed for every dispatch when the case has
  ``expect_person`` and reported for information only on a reuse; failure reasons cite it only when
  a ``create`` outcome is acceptable. Likewise a reuse slot's ``@person`` (``single_slot`` puts the
  case's ``expect_person`` there) is never checked.
- ``over_clarify`` is raised when the observed kind is ``"clarify"`` and ``clarify`` is not
  acceptable, so a correct answer from unique facts alone is not over-clarifying.
- Legacy creates count distinct new names (a second call with the same new name reuses it).
- **Ids the IA created this turn** (id modes, Task 13a): the k-th create of a record gets the id
  ``created_agent_id(k)``, the rule the eval's id tool stub uses. A later dispatch to that id is a
  continuation of the create (same unit, instructions appended), not an unknown id. A call counts
  as a create (and takes the next id) only if the tool would have run it: one missing
  ``instructions`` or with any argument besides ``instructions`` / ``agent_id`` / ``name`` fails
  with "Missing required arguments" in both the production tool and the stub, so it is invalid here.

Multi-dispatch turns (``dispatch`` outcomes, Task 5b, ruling R23: graded on structure, not
wording). The string outcomes keep their code paths unchanged; a ``dispatch`` outcome is graded
alongside them:

- **Dispatch units.** Valid ``send_message_to_agent`` calls are grouped into units the same way
  ``reused`` / ``created`` count them: every call to one existing agent is one unit (its
  instructions joined), every non-legacy create is its own unit, and legacy creates with the same
  new name are one unit. Invalid and ambiguous calls make no unit.
- **Filling.** A unit fills a slot if the target matches (same reused id, or a create) and, for
  each ``@person`` on the slot (create slots that start a new person's thread), the unit's
  instructions name that person by full name or by an email address of a contact with that
  display name (contacts of the required agents and of the roster; case-insensitive substring, the
  rule ``person_ok`` already uses). Reuse and reminder slots need no wording (an ``@person`` on a
  reuse slot is ignored). Mentioning another
  person or a time is never a merge.
- **Pass** iff the units can be assigned one-to-one to the slots with every slot filled and no unit
  left over (exhaustive search, slots <= 4), no ``ambiguous_dispatch``, and, if ``ask``, a user
  message that contains the open first name (the first token of ``clarify_should_name``). In a
  case with such an ``ask`` outcome, its ``clarify`` alternative needs that too, so an
  acknowledgement ("Done, I've asked Sam Rivera.") is not a question. ``clarify_named_ok`` (each name in full or by
  surname as a whole word) is still scored separately. ``slots_filled`` is the size of the best partial assignment.
- **Flags.** With fewer units than slots (failed, outcomes with two or more slots or ``ask``):
  ``merged_intents`` if what was dispatched still covers every slot (a reuse slot: a dispatch to
  its agent, or its "to" contact named; a create slot: its ``@person`` named; a slot with no
  person, i.e. a reminder: a reminder cue in any dispatch, remind / nudge / alert / alarm / notify
  stems or "ping me"), else
  ``dropped_intent``. ``ambiguous_dispatch`` (high severity, partial-ambiguity cases): a
  dispatch's instructions use the open first name without a surname of anyone with that first name
  (email addresses don't count as uses); it fails the case.
- A one-slot dispatch without ``ask`` is exactly ``reuse(id)`` / ``create`` with ``expect_person``
  and grades identically to it (same pass, kind, flags).
- **Time normaliser** (``times_in``): no longer used by labels, kept and tested. Accepted forms:
  ``9pm``, ``9 pm``, ``9PM``, ``9 p.m.``, ``9:00 PM``, ``9.00 pm``, ``9:30pm`` (hour 1-12 with
  am/pm; ``12am`` = 00:00, ``12pm`` = 12:00); 24-hour ``21:00`` / ``09:00`` (a leading zero or an
  hour of 13-23 is unambiguous; ``9:00`` without am/pm means 09:00 or 21:00); ``9 o'clock`` (09:00
  or 21:00); ``noon`` / ``midday`` (12:00) and ``midnight`` (00:00). A **bare hour** (after at / by
  / to / until / till / around / before / after, and not followed by a word such as "people" or
  "days") means 09:00 or 21:00, and counts only when it is the only time expression in the text.
  Digits glued to letters or ``:`` (``T21:00``, ``19pm``) never match.
- ``duplicate_create`` generalises "every acceptable outcome is a reuse": it is raised when every
  acceptable outcome is ``reuse`` or a dispatch with at least one reuse slot, and more agents were
  created than the most create slots any of them allows. ``trigger_duplicate`` is also raised when
  a reuse slot's target that was not reused has a trigger (a second reminder was created).
- ``over_clarify`` is not raised when an acceptable dispatch outcome requires ``ask``.
- ``outcome_kind`` of a passing dispatch outcome is ``"dispatch"``, except a one-slot dispatch
  without ``ask``, which reports its slot's ``reuse`` / ``create``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from evals.schema import AgentDef, Case, Outcome, Slot

ROSTER_MODES = ("legacy", "full", "hybrid")
# Eval-only ablation: today's names-only roster and ``agent_name`` tool, but the new routing rules in
# ``system_prompt.md``. It separates what the prompt rules are worth from what ids and rich agent
# cards add in ``full`` (Siddharth, 2026-11-07).
EVAL_MODES = ROSTER_MODES + ("legacy_rules",)
# Modes whose IA dispatches by ``agent_name`` (names-only roster, legacy tool schemas).
NAME_DISPATCH_MODES = frozenset({"legacy", "legacy_rules"})
DISPATCH = "send_message_to_agent"
USER_MESSAGE = "send_message_to_user"
_ID_DISPATCH_ARGS = frozenset({"instructions", "agent_id", "name"})
FLAGS = frozenset({"duplicate_create", "trigger_duplicate", "wrong_reuse", "over_clarify", "invalid_call",
                   "dropped_intent", "merged_intents", "ambiguous_dispatch"})


def created_agent_id(k: int) -> str:
    """The id the eval's id tool stub gives the ``k``-th agent created in a record (k = 1 first)."""
    return f"ag_new{k:05d}"


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict


@dataclass
class RunRecord:
    case_id: str
    mode: str
    n: int
    run_idx: int
    calls: list[ToolCall]
    user_messages: list[str]
    final_text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    round_trips: int
    error: Optional[str]
    # hybrid only: every ``search_agents`` call as {query, ids, error}, and the ids shown up front
    searches: list[dict[str, Any]] = field(default_factory=list)
    initial_ids: list[str] = field(default_factory=list)


@dataclass
class Dispatch:
    """One dispatch unit: every call to one target (see the module docstring)."""
    target: str  # "create" or "reuse(<agent_id>)"
    name: str  # the new agent's name for a create, "" for a reuse
    instructions: str


@dataclass
class Classified:
    reused: set[str] = field(default_factory=set)
    created: int = 0
    instructions: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    ambiguous_names: list[str] = field(default_factory=list)
    dispatches: list[Dispatch] = field(default_factory=list)


@dataclass
class Grade:
    passed: bool
    outcome_kind: str
    person_ok: Optional[bool]
    clarify_named_ok: Optional[bool]
    set_recall: Optional[float]
    set_precision: Optional[float]
    structural: bool
    flags: set[str]
    slots_filled: Optional[int] = None
    slots_total: Optional[int] = None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _arg(args: dict, key: str) -> str:
    v = args.get(key)
    return v.strip() if isinstance(v, str) else ""


def classify(calls: list[ToolCall], roster: list[AgentDef], mode: str) -> Classified:
    """Resolve every ``send_message_to_agent`` call to reuse / create / invalid / ambiguous."""
    if mode not in EVAL_MODES:
        raise ValueError(f"unknown roster mode {mode!r}")
    out = Classified()
    ids = {a.id for a in roster}
    by_name: dict[str, list[str]] = {}
    for a in roster:
        by_name.setdefault(_norm(a.name), []).append(a.id)
    new_names: set[str] = set()
    units: dict[tuple[str, str], Dispatch] = {}
    created_ids: dict[str, tuple[str, str]] = {}  # id-mode: created id -> its create unit's key

    def unit(key: tuple[str, str], target: str, name: str, instructions: str) -> None:
        if key in units:
            units[key].instructions += "\n" + instructions
        else:
            units[key] = Dispatch(target, name, instructions)

    for i, call in enumerate(calls):
        if call.name != DISPATCH:
            continue
        instructions = call.args.get("instructions")
        instructions = instructions if isinstance(instructions, str) else ""
        if mode in NAME_DISPATCH_MODES:
            name = _arg(call.args, "agent_name")
            if not name:
                out.invalid.append(f"call {i}: legacy dispatch without agent_name")
                continue
            matches = by_name.get(_norm(name), [])
            if len(matches) == 1:
                out.reused.add(matches[0])
                unit(("reuse", matches[0]), f"reuse({matches[0]})", "", instructions)
            elif len(matches) > 1:
                out.ambiguous_names.append(name)
            else:
                if _norm(name) not in new_names:
                    new_names.add(_norm(name))
                    out.created += 1
                unit(("create", _norm(name)), "create", name, instructions)
        else:
            unexpected = sorted(set(call.args) - _ID_DISPATCH_ARGS)
            if unexpected:
                out.invalid.append(f"call {i}: unexpected argument(s) {', '.join(unexpected)}")
                continue
            if "instructions" not in call.args:
                out.invalid.append(f"call {i}: missing instructions")
                continue
            aid, name = _arg(call.args, "agent_id"), _arg(call.args, "name")
            if aid and name:
                out.invalid.append(f"call {i}: both agent_id and name")
                continue
            if not aid and not name:
                out.invalid.append(f"call {i}: neither agent_id nor name")
                continue
            if aid in created_ids:
                key = created_ids[aid]
                unit(key, "create", units[key].name, instructions)
            elif aid and aid not in ids:
                out.invalid.append(f"call {i}: unknown agent_id {aid!r}")
                continue
            elif aid:
                out.reused.add(aid)
                unit(("reuse", aid), f"reuse({aid})", "", instructions)
            else:
                out.created += 1
                key = ("create", str(i))
                created_ids[created_agent_id(out.created)] = key
                unit(key, "create", name, instructions)
        out.instructions.append(instructions)
    out.dispatches = list(units.values())
    return out


def _user_texts(record: RunRecord) -> list[str]:
    texts = list(record.user_messages)
    for call in record.calls:
        if call.name == USER_MESSAGE:
            msg = call.args.get("message")
            if isinstance(msg, str) and msg not in texts:
                texts.append(msg)
    if not texts and record.final_text.strip():
        texts.append(record.final_text)   # production delivers the last assistant text when nothing was sent
    return [t for t in texts if t.strip()]


def _person_ok(case: Case, instructions: list[str]) -> Optional[bool]:
    if case.expect_person is None or not instructions:
        return None
    person = _norm(case.expect_person)
    needles = {person} | {
        _norm(c.email)
        for a in case.required_agents
        for c in a.contacts
        if _norm(c.display_name) == person and c.email.strip()
    }
    return any(n in _norm(text) for text in instructions for n in needles)


def _fact_covered(facts: dict[str, str], haystack: str) -> set[str]:
    return {aid for aid, fact in facts.items() if fact.strip() and _norm(fact) in haystack}


# ------------------------------------------------------------------ slot terms

_EXPLICIT_TIME_RE = re.compile(
    r"(?<![\w:.,$])(?:"
    r"(?P<h1>\d{1,2})(?:[:.](?P<m1>[0-5]\d))?\s?(?P<ap>[ap])\.?\s?m\b\.?"
    r"|(?P<h2>\d{1,2}):(?P<m2>[0-5]\d)(?![\d:])"
    r"|(?P<h3>\d{1,2})\s?o['’]?\s?clock\b"
    r"|(?P<noon>\b(?:noon|midday)\b)|(?P<midnight>\bmidnight\b)"
    r")", re.I)
_BARE_HOUR_RE = re.compile(
    r"\b(?:at|by|to|until|till|around|before|after)\s+(?P<h>\d{1,2})(?![\w:]|[.,]\d)"
    r"(?!\s+(?!(?:instead|tonight|tomorrow|today|this|next|on|sharp|please|and|then|so|for|in|or|to)\b)[a-z])",
    re.I)


def _either(h: int, m: int) -> set[str]:
    """An hour without am/pm: the morning and the evening reading."""
    return {f"{h % 12:02d}:{m:02d}", f"{h % 12 + 12:02d}:{m:02d}"}


def times_in(text: str) -> list[set[str]]:
    """Every time expression in ``text`` as the set of HH:MM (24h) values it can mean."""
    out: list[set[str]] = []
    spans: list[tuple[int, int]] = []
    for m in _EXPLICIT_TIME_RE.finditer(text):
        spans.append(m.span())
        if m.group("noon"):
            out.append({"12:00"})
        elif m.group("midnight"):
            out.append({"00:00"})
        elif m.group("h1"):
            h, mi = int(m.group("h1")), int(m.group("m1") or 0)
            if 1 <= h <= 12:
                out.append({f"{h % 12 + (12 if m.group('ap').lower() == 'p' else 0):02d}:{mi:02d}"})
        elif m.group("h2"):
            raw, h, mi = m.group("h2"), int(m.group("h2")), int(m.group("m2"))
            if h <= 23:
                out.append({f"{h:02d}:{mi:02d}"} if (raw.startswith("0") or h == 0 or h >= 13) else _either(h, mi))
        elif m.group("h3"):
            h = int(m.group("h3"))
            if 1 <= h <= 12:
                out.append(_either(h, 0))
    bare = [m for m in _BARE_HOUR_RE.finditer(text)
            if not any(a <= m.start("h") < b for a, b in spans) and 1 <= int(m.group("h")) <= 12]
    if not out and len(bare) == 1:  # a bare hour counts only when it is the only time in the text
        out.append(_either(int(bare[0].group("h")), 0))
    return out


def mentions_time(text: str, hhmm: str) -> bool:
    return any(hhmm in t for t in times_in(text))


def _person_needles(name: str, contacts: Iterable) -> set[str]:
    person = _norm(name)
    return {person} | {_norm(c.email) for c in contacts if _norm(c.display_name) == person and c.email.strip()}


def _names(person: str, text: str, contacts: list) -> bool:
    """``text`` names ``person`` by full name or one of their email addresses (case-insensitive)."""
    low = _norm(text)
    return any(n in low for n in _person_needles(person, contacts))


def _fills(d: Dispatch, slot: Slot, contacts: list) -> bool:
    """Same target, and on a create slot every ``@person`` named (a reuse slot's person is not checked)."""
    persons = () if slot.reuse_id else slot.persons
    return d.target == slot.target and all(_names(p, d.instructions, contacts) for p in persons)


REMINDER_CUE = re.compile(r"\b(?:remind\w*|nudg\w*|alert\w*|alarm\w*|notif\w*|ping me)\b", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _names_candidate(name: str, text: str) -> bool:
    """True if ``text`` has the full name, or its last token (surname) as a whole word."""
    n, t = _norm(name), _norm(text)
    if n in t:
        return True
    tokens = n.split()
    if len(tokens) < 2:
        return False
    return re.search(rf"\b{re.escape(tokens[-1])}\b", t, re.IGNORECASE) is not None


def _ambiguous_firsts(case: Case) -> set[str]:
    """The first names a partial-ambiguity case leaves open (cases with a dispatch outcome that asks)."""
    if not any(o.kind == "dispatch" and o.ask for o in case.acceptable):
        return set()
    return {n.split()[0] for n in case.clarify_should_name if n.split()}


def _word(word: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.I) is not None


def _bare_first_name(first: str, text: str, contacts: list) -> bool:
    """``text`` uses ``first`` without a surname of anyone called ``first`` (emails don't count)."""
    surnames = {c.display_name.split()[-1] for c in contacts
                if len(c.display_name.split()) > 1 and _norm(c.display_name.split()[0]) == _norm(first)}
    text = _EMAIL_RE.sub(" ", text)
    for m in re.finditer(rf"(?<!\w){re.escape(first)}(?!\w)", text, re.I):
        nxt = re.match(r"\s+([\w'’-]+)", text[m.end():])
        if not (nxt and any(_norm(nxt.group(1)) == _norm(sn) for sn in surnames)):
            return True
    return False


def _slot_covered(slot: Slot, units: list[Dispatch], contacts: list, by_id: dict[str, AgentDef]) -> bool:
    """Diagnostic for a short turn: the slot's work was sent somewhere. A reuse slot is covered by a
    dispatch to its agent or by naming its person; a create slot by naming its person; a slot with
    no person (a reminder) by a reminder cue in any dispatch."""
    text = "\n".join(d.instructions for d in units)
    if slot.reuse_id and any(d.target == slot.target for d in units):
        return True
    people = list(slot.persons)
    if not people and slot.reuse_id and slot.reuse_id in by_id:
        people = [c.display_name for c in by_id[slot.reuse_id].contacts if c.role == "to"]
    if people:
        return any(_names(p, text, contacts) for p in people)
    return REMINDER_CUE.search(text) is not None


def _best_assignment(fill: list[list[bool]], n_units: int) -> int:
    """Most slots filled by distinct units (``fill[slot][unit]``), by exhaustive search."""
    def best(j: int, used: frozenset[int]) -> int:
        if j == len(fill):
            return 0
        top = best(j + 1, used)
        for u in range(n_units):
            if u not in used and fill[j][u] and top < len(fill) - j:
                top = max(top, 1 + best(j + 1, used | {u}))
        return top
    return best(0, frozenset())


def _is_multi(o: Outcome) -> bool:
    """A dispatch outcome that is not just a one-slot reuse/create."""
    return o.kind == "dispatch" and (len(o.slots) > 1 or o.ask)


def grade(case: Case, record: RunRecord, roster: list[AgentDef], mode: str) -> Grade:
    c = classify(record.calls, roster, mode)
    user_texts = _user_texts(record)
    haystack = _norm(" \n ".join([*user_texts, record.final_text or ""]))
    any_dispatch_call = any(call.name == DISPATCH for call in record.calls)
    structural = bool(c.ambiguous_names)
    person_ok = _person_ok(case, c.instructions)

    facts_covered = _fact_covered(case.unique_facts, haystack)
    contacts = [ct for a in [*case.required_agents, *roster] for ct in a.contacts]
    units = c.dispatches

    def slot_fill(o: Outcome) -> list[list[bool]]:
        return [[_fills(d, s, contacts) for d in units] for s in o.slots]

    def filled(o: Outcome) -> int:
        return _best_assignment(slot_fill(o), len(units))

    # Partial ambiguity: the open first name must be asked about, and no dispatch may use it bare.
    ambiguous = _ambiguous_firsts(case)
    asked = any(_word(f, t) for f in ambiguous for t in user_texts) if ambiguous else bool(user_texts)
    ambiguous_dispatch = any(_bare_first_name(f, d.instructions, contacts) for f in ambiguous for d in units)

    def set_metrics(o: Outcome) -> tuple[float, Optional[float]]:
        expected = set(o.agent_ids)
        recall = len((c.reused | facts_covered) & expected) / len(expected)
        precision = len(c.reused & expected) / len(c.reused) if c.reused else None
        return recall, precision

    def matches(o: Outcome) -> bool:
        if o.kind == "reuse":  # expect_person is not checked on a reuse (see the module docstring)
            return c.reused == {o.agent_ids[0]} and c.created == 0
        if o.kind == "create":
            return c.created == 1 and not c.reused and person_ok is not False
        if o.kind == "clarify":
            return not any_dispatch_call and asked
        if o.kind == "dispatch":
            return (len(units) == len(o.slots) and filled(o) == len(o.slots) and not ambiguous_dispatch
                    and (asked or not o.ask))
        recall, _ = set_metrics(o)
        return recall == 1.0 and c.reused <= set(o.agent_ids) and c.created == 0

    # Set metrics are reported for the case's first answer_set outcome, if any.
    first_set = next((o for o in case.acceptable if o.kind == "answer_set"), None)
    set_recall, set_precision = set_metrics(first_set) if first_set else (None, None)

    # Any user message satisfies clarify, so a more specific match (e.g. answer_set) wins.
    hits = [o for o in case.acceptable if matches(o)]
    matched = next((o for o in hits if o.kind != "clarify"), hits[0] if hits else None)
    passed = matched is not None and not structural

    if passed and matched.kind == "dispatch":
        outcome_kind = "dispatch" if _is_multi(matched) else ("reuse" if matched.slots[0].reuse_id else "create")
    elif passed:
        outcome_kind = matched.kind
    elif c.reused and c.created:
        outcome_kind = "mixed"
    elif c.reused:
        outcome_kind = "reuse"
    elif c.created:
        outcome_kind = "create"
    elif any_dispatch_call:  # dispatch attempted, but every call was invalid or ambiguous
        outcome_kind = "invalid"
    elif facts_covered:
        outcome_kind = "answer_set"
    elif user_texts:
        outcome_kind = "clarify"
    else:
        outcome_kind = "none"

    kinds = {o.kind for o in case.acceptable}
    acceptable_ids = {aid for o in case.acceptable for aid in o.agent_ids}
    dispatch_outcomes = [o for o in case.acceptable if o.kind == "dispatch"]
    flags: set[str] = set()
    # "Every acceptable outcome is a reuse", generalised to dispatch outcomes with a reuse slot.
    reuse_like = all(o.kind == "reuse" or (o.kind == "dispatch" and o.agent_ids) for o in case.acceptable)
    creates_allowed = max(sum(not s.reuse_id for s in o.slots) for o in case.acceptable) if reuse_like else 0
    if c.created and reuse_like and c.created > creates_allowed:
        flags.add("duplicate_create")
        by_id = {a.id: a for a in roster}
        missed_trigger = any(aid not in c.reused and by_id.get(aid) is not None and by_id[aid].triggers
                             for o in dispatch_outcomes for aid in o.agent_ids)
        if case.category == "trigger_management" or missed_trigger:
            flags.add("trigger_duplicate")
    if c.reused - acceptable_ids:
        flags.add("wrong_reuse")
    if outcome_kind == "clarify" and "clarify" not in kinds and not any(o.ask for o in dispatch_outcomes):
        flags.add("over_clarify")
    if c.invalid:
        flags.add("invalid_call")
    if ambiguous_dispatch:
        flags.add("ambiguous_dispatch")

    slots_filled = slots_total = None
    if dispatch_outcomes:
        if passed and matched.kind == "dispatch":
            best = matched
        elif passed:
            best = None  # passed through another acceptable outcome (e.g. clarify)
        else:
            best = max(dispatch_outcomes, key=filled)  # first of the best on ties
        if best is not None:
            slots_filled, slots_total = filled(best), len(best.slots)
            if not passed and _is_multi(best) and len(units) < len(best.slots):
                # Fewer dispatches than slots: merged if what was sent still covers every slot
                # (each slot's person, or a reminder cue for a slot with no person), else dropped.
                by_id = {a.id: a for a in [*case.required_agents, *roster]}
                covered = bool(units) and all(_slot_covered(sl, units, contacts, by_id) for sl in best.slots)
                flags.add("merged_intents" if covered else "dropped_intent")

    clarify_named_ok: Optional[bool] = None
    if case.clarify_should_name:
        clarify_named_ok = all(
            any(_names_candidate(name, t) for t in user_texts) for name in case.clarify_should_name
        )

    return Grade(
        passed=passed,
        outcome_kind=outcome_kind,
        person_ok=person_ok,
        clarify_named_ok=clarify_named_ok,
        set_recall=set_recall,
        set_precision=set_precision,
        structural=structural,
        flags=flags,
        slots_filled=slots_filled,
        slots_total=slots_total,
    )
