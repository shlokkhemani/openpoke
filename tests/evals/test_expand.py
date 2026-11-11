import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from evals.baselines import always_ask, always_create, always_reuse_top, oracle
from evals.expand import expand
from evals.grading import grade
from evals.schema import CATEGORIES, _colliding_contacts, case_to_dict, load_cases, validate_cases
from evals.world.roster import FACT_RE, load_world, roster_for

EX = Path("evals/cases/examples")
WORLD = load_world(Path("evals/world/world.json"))
EXAMPLES = load_cases(EX)
CASES = expand(WORLD, EXAMPLES)
BY_ID = {c.id: c for c in CASES}
GENERATED = [c for c in CASES if c.source == "template"]

TEST_COUNTS = {
    "email_followup": 4, "new_task_lookalike": 4, "ambiguous_person": 5, "clear_person": 4,
    "trigger_management": 4, "broad_question_person": 4, "multi_person": 4, "multi_intent": 4,
}


def test_counts_and_split_v2():
    assert Counter(c.category for c in CASES if c.split == "test") == TEST_COUNTS
    assert Counter(c.category for c in CASES if c.split == "dev") == {k: 2 for k in CATEGORIES}
    assert len(CASES) == 49
    assert validate_cases(CASES) == []


def test_examples_are_kept_unchanged_and_generated_are_templates():
    hand = [c for c in CASES if c.source == "hand"]
    assert [case_to_dict(c) for c in hand] == [case_to_dict(c) for c in EXAMPLES]
    assert all(c.split == "test" for c in hand)
    assert len(GENERATED) == 38
    assert all(c.original_message is None for c in CASES)


def test_deterministic_and_seeded():
    assert [case_to_dict(c) for c in expand(WORLD, EXAMPLES)] == [case_to_dict(c) for c in CASES]
    other = expand(WORLD, EXAMPLES, seed=8)
    assert [c.message for c in other] != [c.message for c in CASES]


def test_required_agents_are_world_agents_and_bounded():
    for c in CASES:
        assert 1 <= len(c.required_agents) <= 10, c.id
        for a in c.required_agents:
            assert WORLD.agents[a.id] == a, (c.id, a.id)


def test_messages_are_distinct():
    msgs = [c.message for c in GENERATED]
    assert len(set(msgs)) >= len(msgs) - 4  # a few shared templates across splits are fine


def _named_contacts(case):
    """World contacts whose first name or full name appears in the case's text."""
    text = " ".join([case.message, case.expect_person or "", *case.clarify_should_name,
                     *(t.text for t in case.ia_history)])
    firsts = {c.display_name.split()[0] for c in WORLD.contacts
              if re.search(rf"(?<!\w){re.escape(c.display_name.split()[0])}(?!\w)", text)}
    return [c for c in WORLD.contacts if c.display_name.split()[0] in firsts]


def test_label_safety_every_person_named_has_all_agents_required():
    for c in GENERATED:  # hand examples are the controller's; followup-001 deliberately omits ag_dana_parking
        required = {a.id for a in c.required_agents}
        emails = {ct.email.lower() for ct in _named_contacts(c)}
        for aid, agent in WORLD.agents.items():
            if aid in required:
                continue
            shared = emails & {ct.email.lower() for ct in agent.contacts}
            assert not shared, f"{c.id}: non-required {aid} shares contact {shared}"


def test_no_unrequired_twin_of_a_reuse_target():
    for c in GENERATED:
        required = {a.id for a in c.required_agents}
        for o in c.acceptable:
            if o.kind not in ("reuse", "dispatch"):
                continue
            for aid in o.agent_ids:
                target = WORLD.agents[aid]
                twins = [a.id for a in WORLD.agents.values()
                         if a.name == target.name and a.id not in required]
                assert not twins, f"{c.id}: unrequired same-name agents {twins}"


def test_ambiguous_cases_have_a_clear_pair():
    clear = [c for c in CASES if c.category == "clear_person"]
    for c in CASES:
        if c.category != "ambiguous_person":
            continue
        colliding = _colliding_contacts(c)
        assert colliding, c.id
        firsts = {ct.display_name.split()[0] for ct in colliding}
        for first in firsts:
            names = {ct.display_name for ct in colliding if ct.display_name.split()[0] == first}
            assert any(
                k.expect_person in names and k.expect_person in k.message for k in clear
            ), f"{c.id}: no clear_person case names one of {names} in full"


def test_ambiguous_variants_cover_both_directions():
    amb = [c for c in CASES if c.category == "ambiguous_person"]
    kinds = {c.acceptable[0].kind for c in amb}
    assert {"clarify", "create", "reuse"} <= kinds
    assert any(re.search(r"\b(her|him|them)\b", c.message) for c in amb)


def test_trigger_cases_have_context_and_lookalikes():
    trig = [c for c in GENERATED if c.category == "trigger_management"]
    assert any(any(t.role == "agent" and t.agent_id for t in c.ia_history) for c in trig)
    for c in trig:
        assert c.severity == "high"
        target = WORLD.agents[c.acceptable[0].agent_ids[0]]
        assert target.triggers
        assert len(c.required_agents) >= 2


def test_broad_cases_use_code_facts_and_cover_the_person():
    broad = [c for c in GENERATED if c.category == "broad_question_person"]
    for c in broad:
        o = c.acceptable[0]
        assert o.kind == "answer_set" and len(o.agent_ids) >= 3
        assert c.unique_facts
        for fact in c.unique_facts.values():
            assert FACT_RE.fullmatch(fact) and not fact.startswith("$"), (c.id, fact)


def _rank(case, n):
    roster = roster_for(case, WORLD, n)
    target = case.acceptable[0].agent_ids[0]
    act = {a.id: a.last_user_activity_days_ago for a in roster}
    return sum(1 for v in act.values() if v < act[target])


@pytest.mark.parametrize("n", [100, 300])
def test_long_tail_present_at_every_n(n):
    reuse = [c for c in CASES if c.split == "test" and c.acceptable[0].kind == "reuse"
             and c.category in ("email_followup", "trigger_management")]
    tail = [c.id for c in reuse if _rank(c, n) >= 20]
    # 8 such test cases (was 16, threshold 6); the threshold keeps the same proportion: 3 of 8.
    assert len(reuse) == 8 and len(tail) >= 3, tail


def test_target_is_not_always_the_most_recent_agent():
    reuse = [c for c in GENERATED if c.acceptable[0].kind == "reuse" and c.category == "email_followup"]
    not_newest = [
        c for c in reuse
        if min(a.last_user_activity_days_ago for a in c.required_agents)
        < WORLD.agents[c.acceptable[0].agent_ids[0]].last_user_activity_days_ago
    ]
    assert len(not_newest) >= len(reuse) // 2


def _pass_rate(fn, n=30, cases=None):
    cases = CASES if cases is None else cases
    ok = 0
    for c in cases:
        roster = roster_for(c, WORLD, n)
        ok += grade(c, fn(c, roster), roster, "full").passed
    return ok / len(cases)


def test_oracle_passes_everything_and_always_baselines_fail():
    assert _pass_rate(oracle) == 1.0
    assert _pass_rate(always_create) < 0.5
    assert _pass_rate(always_ask) < 0.5


def test_always_reuse_top_by_recency_scores_poorly():
    def top(c, roster):
        ranked = sorted(roster, key=lambda a: a.last_user_activity_days_ago)
        return always_reuse_top(c, roster, [a.id for a in ranked])

    assert _pass_rate(top) < 0.5


def test_oracle_passes_at_every_roster_size():
    for n in (10, 30, 100, 300):
        for c in CASES:
            roster = roster_for(c, WORLD, n)
            assert grade(c, oracle(c, roster), roster, "full").passed, (c.id, n)


@pytest.mark.parametrize("n", [10, 30, 300])
def test_oracle_100_baselines_low_v2(n):
    assert _pass_rate(oracle, n) == 1.0
    assert _pass_rate(always_create, n) < 0.5
    assert _pass_rate(always_ask, n) < 0.5
    multi = [c for c in CASES if c.category in ("multi_person", "multi_intent")]
    assert _pass_rate(always_create, n, multi) == 0.0


# ------------------------------------------------------------------ multi-dispatch categories

MULTI = [c for c in CASES if c.category in ("multi_person", "multi_intent")]


def _targets(o):
    return tuple(sorted("reuse" if s.reuse_id else "create" for s in o.slots))


def _dispatch(c):
    return next(o for o in c.acceptable if o.kind == "dispatch")


def _person_of(slot):
    """The person a slot is for: its @person, or the 'to' contact of its reuse target (None: reminder)."""
    if slot.persons:
        return slot.persons[0]
    if slot.reuse_id:
        to = [c.display_name for c in WORLD.agents[slot.reuse_id].contacts if c.role == "to"]
        return to[0] if to else None
    return None


def test_multi_person_shapes():
    mp = [c for c in CASES if c.category == "multi_person"]
    shapes = {_targets(_dispatch(c)) for c in mp if not _dispatch(c).ask}
    assert ("create", "reuse") in shapes and ("create", "create") in shapes
    partial = [c for c in mp if _dispatch(c).ask]
    assert partial and any(c.split == "test" for c in partial)
    for c in partial:
        assert [o.kind for o in c.acceptable] == ["clarify", "dispatch"], c.id
        ambiguous_first = {n.split()[0] for n in c.clarify_should_name}
        assert len(c.clarify_should_name) >= 2 and len(ambiguous_first) == 1, c.id
        assert re.search(rf"\b{ambiguous_first.pop()}\b", c.message), c.id
        assert c.severity == "high"
    for c in mp:
        people = [_person_of(s) for s in _dispatch(c).slots]
        assert None not in people and len(set(people)) == len(people), c.id  # one agent per person
        assert len(people) == (1 if _dispatch(c).ask else 2), c.id


def test_multi_intent_shapes():
    mi = [c for c in CASES if c.category == "multi_intent"]
    reminder_reuse = email_reuse = 0
    for c in mi:
        o = _dispatch(c)
        assert len(c.acceptable) == 1 and not o.ask and len(o.slots) == 2, c.id
        email, reminder = o.slots
        assert _person_of(email) and _person_of(reminder) is None, c.id
        assert not reminder.must_mention, c.id  # R23: reminder slots carry no terms
        if reminder.reuse_id:
            reminder_reuse += 1
            assert WORLD.agents[reminder.reuse_id].triggers and c.severity == "high"
        if email.reuse_id:
            email_reuse += 1
            assert not WORLD.agents[email.reuse_id].triggers
    assert reminder_reuse >= 1 and email_reuse >= 1


def test_multi_slots_are_structural():
    """R23: @person only on create slots, and it is named in the message; nothing else is a term."""
    for c in MULTI:
        for s in _dispatch(c).slots:
            if s.reuse_id:
                assert not s.must_mention, c.id
            for name in s.persons:
                assert name in c.message, (c.id, name)


def test_multi_label_safety_reminders():
    """A reminder reuse target has no same-subject twin anywhere in the world."""
    from evals.expand import _trig

    for c in MULTI:
        for s in _dispatch(c).slots:
            if s.reuse_id and WORLD.agents[s.reuse_id].triggers:
                t = _trig(WORLD.agents[s.reuse_id])
                twins = [a.id for a in WORLD.agents.values() if a.id != s.reuse_id and (u := _trig(a))
                         and u.kind == t.kind and u.group == t.group]
                assert not twins, (c.id, twins)


def test_merged_single_dispatch_fails_every_multi_case():
    from evals.baselines import _record
    from evals.grading import DISPATCH, ToolCall

    for c in MULTI:
        o = _dispatch(c)
        if o.ask:
            continue
        roster = roster_for(c, WORLD, 30)
        people = [p for s in o.slots if (p := _person_of(s))]
        text = "Handle all of it: " + " and ".join(people) + (", and remind me" if len(people) < len(o.slots) else "")
        for call in [ToolCall(DISPATCH, {"name": "All of it", "instructions": text})] + [
                ToolCall(DISPATCH, {"agent_id": s.reuse_id, "instructions": text}) for s in o.slots if s.reuse_id]:
            g = grade(c, _record(c, roster, "merged", [call]), roster, "full")
            assert not g.passed and "merged_intents" in g.flags, (c.id, call)


def test_partial_ambiguity_ack_only_fails_every_case():
    from evals.baselines import _record
    from evals.grading import DISPATCH, USER_MESSAGE, ToolCall

    for c in MULTI:
        o = _dispatch(c)
        if not o.ask:
            continue
        roster = roster_for(c, WORLD, 30)
        (slot,) = o.slots
        sent = ToolCall(DISPATCH, {"name": "x", "instructions": f"Ask {slot.persons[0]}"})
        first = c.clarify_should_name[0].split()[0]
        ack = _record(c, roster, "ack", [sent, ToolCall(USER_MESSAGE, {"message": f"Done, asked {slot.persons[0]}."})])
        good = _record(c, roster, "ok", [sent, ToolCall(USER_MESSAGE, {"message": f"Which {first}?"})])
        assert not grade(c, ack, roster, "full").passed and grade(c, good, roster, "full").passed, c.id
