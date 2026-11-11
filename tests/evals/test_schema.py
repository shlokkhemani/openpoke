import json
from pathlib import Path

from evals.clock import EVAL_NOW, days_ago
from evals.schema import (
    CATEGORIES,
    Outcome,
    Slot,
    load_cases,
    outcome_to_json,
    parse_outcome,
    save_case,
    single_slot,
    validate_cases,
)

EX = Path("evals/cases/examples")


def agent(aid, desc="Sent the quarterly report to the finance team.", contacts=None, **kw):
    d = {
        "id": aid,
        "name": f"name {aid}",
        "description": desc,
        "contacts": contacts or [],
        "last_user_activity_days_ago": 1,
    }
    d.update(kw)
    return d


def write(tmp_path, cid, agents, message="Please look into it.", acceptable=("create",),
          category="email_followup", **extra):
    d = {
        "id": cid,
        "category": category,
        "split": "dev",
        "source": "hand",
        "severity": "normal",
        "required_agents": agents,
        "message": message,
        "ia_history": [],
        "acceptable": list(acceptable),
    }
    d.update(extra)
    (tmp_path / f"{cid}.json").write_text(json.dumps(d))


def contact(email, name):
    return {"email": email, "display_name": name, "role": "to"}


def test_examples_load():
    cases = load_cases(EX)
    assert len(cases) == 11
    assert {c.category for c in cases} == set(CATEGORIES) - {"multi_person", "multi_intent"}


def test_categories_include_multi_dispatch():
    assert len(CATEGORIES) == 8 and {"multi_person", "multi_intent"} <= set(CATEGORIES)


def test_examples_validate_clean():
    assert validate_cases(load_cases(EX)) == []


def test_examples_round_trip(tmp_path):
    cases = load_cases(EX)
    for c in cases:
        save_case(c, tmp_path / f"{c.id}.json")
    assert load_cases(tmp_path) == sorted(cases, key=lambda c: c.id)


def test_clock():
    assert EVAL_NOW.isoformat() == "2026-11-01T12:00:00+00:00"
    assert (EVAL_NOW - days_ago(2.5)).total_seconds() == 2.5 * 86400


def test_parse_outcomes():
    assert parse_outcome("reuse(ag_x)") == Outcome("reuse", ("ag_x",))
    assert parse_outcome("answer_set([a, b])") == Outcome("answer_set", ("a", "b"))
    assert parse_outcome("clarify") == Outcome("clarify", ())
    assert parse_outcome("create") == Outcome("create", ())


def test_conflicting_agent_definitions_rejected(tmp_path):
    write(tmp_path, "c1", [agent("ag_dup", "Sent the quarterly report to finance.")])
    write(tmp_path, "c2", [agent("ag_dup", "Booked a table for four on Friday.")])
    assert any("ag_dup" in p for p in validate_cases(load_cases(tmp_path)))


def test_identical_agent_definitions_ok(tmp_path):
    write(tmp_path, "c1", [agent("ag_same")])
    write(tmp_path, "c2", [agent("ag_same")])
    assert validate_cases(load_cases(tmp_path)) == []


def test_duplicate_case_id_and_bad_category(tmp_path):
    write(tmp_path, "c1", [agent("ag_a")], category="nonsense")
    (tmp_path / "copy.json").write_text((tmp_path / "c1.json").read_text())
    probs = validate_cases(load_cases(tmp_path))
    assert any("duplicate" in p for p in probs)
    assert any("nonsense" in p for p in probs)


def test_reuse_target_must_be_required(tmp_path):
    write(tmp_path, "c1", [agent("ag_a")], acceptable=["reuse(ag_missing)"])
    assert any("ag_missing" in p for p in validate_cases(load_cases(tmp_path)))


def test_description_wording_not_copied(tmp_path):
    desc = "Emailed the landlord about the broken dishwasher and got a work order."
    write(tmp_path, "c1", [agent("ag_a", desc)], acceptable=["reuse(ag_a)"],
          message="Hey, did the landlord about the broken dishwasher reply?")
    probs = validate_cases(load_cases(tmp_path))
    assert any("copied" in p and "ag_a" in p for p in probs)


def test_short_overlap_is_fine(tmp_path):
    desc = "Emailed the landlord about the broken dishwasher and got a work order."
    write(tmp_path, "c1", [agent("ag_a", desc)], acceptable=["reuse(ag_a)"],
          message="Any news on the broken dishwasher?")
    assert validate_cases(load_cases(tmp_path)) == []


ALICES = [
    agent("ag_1", contacts=[contact("alice.chen@x.io", "Alice Chen")]),
    agent("ag_2", "Asked about dinner plans.", contacts=[contact("alice.park@y.com", "Alice Park")]),
]


def test_ambiguous_person_surname_rejected(tmp_path):
    write(tmp_path, "c1", ALICES, category="ambiguous_person", acceptable=["clarify"],
          message="Email Alice Park about Thursday")
    assert any("Alice Park" in p for p in validate_cases(load_cases(tmp_path)))


def test_ambiguous_person_email_rejected(tmp_path):
    write(tmp_path, "c1", ALICES, category="ambiguous_person", acceptable=["clarify"],
          message="Email alice.chen@x.io about Thursday")
    assert any("alice.chen@x.io" in p for p in validate_cases(load_cases(tmp_path)))


def test_ambiguous_person_create_with_expect_person_exempt(tmp_path):
    write(tmp_path, "c1", ALICES, category="ambiguous_person", acceptable=["create"],
          expect_person="Alice Park", message="Email Alice Park about Thursday")
    assert validate_cases(load_cases(tmp_path)) == []


def test_ambiguous_person_clean_first_name_only(tmp_path):
    write(tmp_path, "c1", ALICES, category="ambiguous_person", acceptable=["clarify"],
          message="Email Alice about Thursday")
    assert validate_cases(load_cases(tmp_path)) == []


def test_unique_facts_checks(tmp_path):
    a = agent("ag_a", "Order number ZX-1 shipped.")
    b = agent("ag_b", "Order number ZX-1 and QQ-2 shipped.")
    write(tmp_path, "c1", [a, b], unique_facts={"ag_a": "ZX-1", "ag_b": "QQ-2", "ag_z": "foo", "ag_c": "bar"})
    write(tmp_path, "c2", [a], unique_facts={"ag_a": "nothere"})
    probs = validate_cases(load_cases(tmp_path))
    assert any("ZX-1" in p and "ag_b" in p for p in probs)  # not unique
    assert any("ag_z" in p for p in probs)  # key not required
    assert any("nothere" in p for p in probs)  # not in description
    assert not any("QQ-2" in p for p in probs)


def test_original_message_round_trip_and_omitted_when_none():
    from evals.schema import case_from_dict, case_to_dict

    case = load_cases(EX)[0]
    assert case.original_message is None
    assert "original_message" not in case_to_dict(case)
    case.original_message = "before"
    d = case_to_dict(case)
    assert d["original_message"] == "before"
    assert case_from_dict(d).original_message == "before"


# ------------------------------------------------------------ dispatch outcomes (Task 5b)

DISPATCH = {"slots": [{"target": "reuse(ag_a)", "must_mention": []},
                      {"target": "create", "must_mention": ["@person:Alice Chen"]}],
            "ask": False}
CHEN = [agent("ag_a", contacts=[contact("alice.chen@x.io", "Alice Chen")])]


def test_parse_dispatch_outcome():
    o = parse_outcome(DISPATCH)
    assert o.kind == "dispatch" and o.ask is False and len(o.slots) == 2
    assert o.slots[0] == Slot("reuse(ag_a)") and o.slots[1] == Slot("create", ("@person:Alice Chen",))
    assert o.slots[0].reuse_id == "ag_a" and o.slots[1].reuse_id is None
    assert o.slots[1].persons == ("Alice Chen",)
    assert o.agent_ids == ("ag_a",)


def test_dispatch_outcome_json_round_trip(tmp_path):
    write(tmp_path, "c1", CHEN, acceptable=["clarify", DISPATCH], category="multi_intent")
    case = load_cases(tmp_path)[0]
    assert outcome_to_json(case.acceptable[1]) == DISPATCH
    assert outcome_to_json(case.acceptable[0]) == "clarify"
    save_case(case, tmp_path / "c1.json")
    assert load_cases(tmp_path)[0] == case
    assert validate_cases([case]) == []


def test_malformed_dispatch_rejected():
    import pytest
    for bad in ({"slots": [{"target": "reuse()", "must_mention": []}], "ask": False},
                {"slots": [{"target": "delete", "must_mention": []}], "ask": False},
                {"slots": [{"target": "create", "must_mention": ["@time:21:00"]}], "ask": False},
                {"slots": [{"target": "create", "must_mention": ["dinner"]}], "ask": False},
                {"slots": [{"target": "create", "must_mention": ["@person:"]}], "ask": False},
                {"slots": [{"target": "create", "must_not_mention": ["Alice"]}], "ask": False},
                {"slots": [{"target": "create"}], "ask": "yes"}):
        with pytest.raises(ValueError):
            parse_outcome(bad)


def test_dispatch_validation(tmp_path):
    bad = {"slots": [{"target": "reuse(ag_missing)", "must_mention": ["@person:Nobody Here"]}], "ask": False}
    write(tmp_path, "c1", CHEN, acceptable=[bad], category="multi_person")
    write(tmp_path, "c2", CHEN, acceptable=[{"slots": [], "ask": False}], category="multi_person")
    many = {"slots": [{"target": "create", "must_mention": []}] * 5, "ask": False}
    write(tmp_path, "c3", CHEN, acceptable=[many], category="multi_person")
    probs = validate_cases(load_cases(tmp_path))
    assert any("c1" in p and "ag_missing" in p for p in probs)
    assert any("c1" in p and "Nobody Here" in p for p in probs)
    assert any("c2" in p and "no slots" in p for p in probs)
    assert any("c3" in p and "slots" in p for p in probs)


SAMS = ALICES + [
    agent("ag_3", "Asked about the vendor contract.", contacts=[contact("sam.rivera@x.io", "Sam Rivera")]),
    agent("ag_4", "Asked about the audit.", contacts=[contact("sam.okafor@y.com", "Sam Okafor")]),
]
PARTIAL = {"slots": [{"target": "create", "must_mention": ["@person:Sam Rivera"]}], "ask": True}


def test_multi_person_partial_ambiguity_surname_check(tmp_path):
    names = ["Alice Chen", "Alice Park"]
    write(tmp_path, "ok", SAMS, category="multi_person", acceptable=["clarify", PARTIAL],
          clarify_should_name=names, message="Ask Alice and Sam Rivera if they're free for coffee")
    write(tmp_path, "bad", SAMS, category="multi_person", acceptable=["clarify", PARTIAL],
          clarify_should_name=names, message="Ask Alice Park and Sam Rivera if they're free for coffee")
    write(tmp_path, "noask", SAMS, category="multi_person",
          acceptable=[{"slots": PARTIAL["slots"], "ask": False}],
          message="Ask Alice Park and Sam Rivera if they're free for coffee")
    probs = validate_cases(load_cases(tmp_path))
    assert not any(p.startswith("ok:") for p in probs), probs
    assert any(p.startswith("bad:") and "Alice Park" in p for p in probs)
    assert not any(p.startswith("noask:") for p in probs), probs


def test_multi_reuse_slot_must_not_name_a_person(tmp_path):
    bad = {"slots": [{"target": "reuse(ag_a)", "must_mention": ["@person:Alice Chen"]}], "ask": False}
    write(tmp_path, "c1", CHEN, acceptable=[bad], category="multi_person")
    two = {"slots": [{"target": "create", "must_mention": ["@person:Alice Chen", "@person:Alice Chen"]}], "ask": False}
    write(tmp_path, "c2", CHEN, acceptable=[two], category="multi_person")
    probs = validate_cases(load_cases(tmp_path))
    assert any(p.startswith("c1:") and "reuse slot" in p for p in probs)
    assert any(p.startswith("c2:") and "more than one person" in p for p in probs)


def test_single_slot_equivalent():
    assert single_slot(Outcome("reuse", ("ag_a",)), "Alice Chen") == Outcome(
        "dispatch", ("ag_a",), (Slot("reuse(ag_a)", ("@person:Alice Chen",)),), False)
    assert single_slot(Outcome("create"), None) == Outcome("dispatch", (), (Slot("create", ()),), False)
