"""Task 16a: ``Case.context_agents``, rosters, retrieval extra agents, regrade dir, one ``CASES_DIR``."""
import dataclasses
import json
import os
import random
from pathlib import Path

import pytest

from evals import caseset
from evals import retrieval_eval as re_mod
from evals import run as run_mod
from evals import run_store
from evals.caseset import load_frozen_cases
from evals.schema import (AgentDef, Outcome, Slot, Turn, case_from_dict, case_to_dict, validate_cases)
from evals.world.generate import WORLD_PATH
from evals.world.roster import _shuffle_seed, load_world, roster_for

REPO = Path(__file__).resolve().parents[2]
V1 = REPO / "evals" / "cases" / "v1"


@pytest.fixture(scope="module")
def world():
    return load_world(WORLD_PATH)


@pytest.fixture(scope="module")
def cases():
    return load_frozen_cases(V1)


def _dump(c):
    return json.dumps(case_to_dict(c), indent=2, ensure_ascii=False) + "\n"


def _filler(world, i=0, skip=()):
    ids = [a for a in world.filler_order if a not in skip]
    return world.agents[ids[i]]


def _with_context(case, agent, text="Here is the update."):
    """``case`` plus a context agent and an agent turn that references it."""
    turns = list(case.ia_history) + [Turn("agent", text, agent.id, agent.name)]
    return dataclasses.replace(case, context_agents=[agent], ia_history=turns)


# ------------------------------------------------------------ 1. round trip

def test_v1_files_round_trip_byte_identically():  # passes today: a guard that v1 output must not change
    files = [p for p in sorted(V1.glob("*.json")) if p.name != "MANIFEST.json"]
    assert len(files) == 49
    for p in files:
        raw = p.read_text(encoding="utf-8")
        assert _dump(case_from_dict(json.loads(raw))) == raw, p.name


def test_context_agents_default_empty_and_absent_from_v1_dicts(cases):
    assert all(c.context_agents == [] for c in cases)
    assert all("context_agents" not in case_to_dict(c) for c in cases)


def test_case_with_context_agent_round_trips_as_the_last_key(cases, world):
    a = _filler(world)
    c = _with_context(cases[0], a)
    d = case_to_dict(c)
    assert list(d)[-1] == "context_agents"
    assert len(d["context_agents"]) == 1
    back = case_from_dict(json.loads(json.dumps(d)))
    assert back.context_agents == [a]
    assert _dump(back) == _dump(c)


# ---------------------------------------------------------------- 2. rosters

def _old_roster(case, world, n):
    """Today's algorithm, inlined (required, then fillers in filler_order, shuffled by (case.id, n))."""
    required = {a.id: a for a in case.required_agents}
    if n < len(required):
        raise ValueError("too small")
    roster = list(required.values())
    for aid in world.filler_order:
        if len(roster) >= n:
            break
        if aid not in required:
            roster.append(world.agents[aid])
    random.Random(_shuffle_seed(case.id, n)).shuffle(roster)
    return roster


@pytest.mark.parametrize("n", [10, 30, 100, 300])
def test_v1_rosters_are_unchanged(cases, world, n):
    assert len(cases) == 49
    for c in cases:
        assert [a.id for a in roster_for(c, world, n)] == [a.id for a in _old_roster(c, world, n)], (c.id, n)


def test_roster_with_context_agent_has_it_once_and_right_length(cases, world):
    c0 = cases[0]
    req = {a.id for a in c0.required_agents}
    a = _filler(world, 3, skip=req)
    c = _with_context(c0, a)
    r = roster_for(c, world, 10)
    ids = [x.id for x in r]
    assert len(r) == 10 and len(set(ids)) == 10
    assert ids.count(a.id) == 1 and req <= set(ids)


def test_context_agent_far_down_filler_order_still_included_at_small_n(cases, world):
    c0 = cases[0]
    req = {a.id for a in c0.required_agents}
    a = world.agents[world.filler_order[-1]]
    ids = [x.id for x in roster_for(_with_context(c0, a), world, 10)]
    assert a.id in ids and len(ids) == 10


def test_context_agent_already_a_required_id_is_not_duplicated(cases, world):
    c0 = cases[0]
    c = dataclasses.replace(c0, context_agents=[c0.required_agents[0]])
    ids = [x.id for x in roster_for(c, world, 10)]
    assert len(ids) == 10 and len(set(ids)) == 10


def test_roster_smaller_than_required_plus_context_raises(cases, world):
    c0 = next(c for c in cases if len(c.required_agents) >= 2)
    k = len(c0.required_agents)
    c = _with_context(c0, _filler(world, 0, skip={a.id for a in c0.required_agents}))
    with pytest.raises(ValueError):
        roster_for(c, world, k)  # fits the required agents alone, not required + context
    assert len(roster_for(c, world, k + 1)) == k + 1


# ------------------------------------------------------------- 3. validation

@pytest.fixture
def base(cases, world):
    """A v1 case with at least one agent turn and a context agent id that no other case uses."""
    c0 = next(c for c in cases if c.id == "followup-001")
    a = _filler(world, 5, skip={x.id for c in cases for x in c.required_agents})
    return c0, a


def _problems(c, *more):
    return validate_cases([c, *more])


def _ctx_problems(problems, aid):
    return [p for p in problems if "context agent" in p and aid in p]


def test_valid_context_agent_adds_no_problems(base):
    c0, a = base
    assert _problems(_with_context(c0, a)) == _problems(c0)


def test_rejected_when_no_agent_turn_references_it(base):
    c0, a = base
    c = dataclasses.replace(c0, context_agents=[a])
    ps = _ctx_problems(_problems(c), a.id)
    assert any(f"{c0.id}: context agent {a.id} is not referenced by an agent turn in ia_history" == p for p in ps)


def test_a_user_turn_carrying_the_id_does_not_count(base):
    c0, a = base
    c = dataclasses.replace(c0, context_agents=[a],
                            ia_history=list(c0.ia_history) + [Turn("user", "hi", a.id, a.name)])
    assert _ctx_problems(_problems(c), a.id)


def test_rejected_when_id_in_required_agents(base):
    c0, _ = base
    req = c0.required_agents[0]
    c = dataclasses.replace(c0, context_agents=[req])
    c = dataclasses.replace(c, ia_history=list(c0.ia_history) + [Turn("agent", "x", req.id, req.name)])
    assert _ctx_problems(_problems(c), req.id)


def test_rejected_when_id_is_a_reuse_outcome_target(base):
    c0, a = base
    c = _with_context(c0, a)
    c = dataclasses.replace(c, acceptable=[*c.acceptable, Outcome("reuse", (a.id,))])
    assert _ctx_problems(_problems(c), a.id)


def test_rejected_when_id_is_a_dispatch_slot_reuse_target(base):
    c0, a = base
    c = _with_context(c0, a)
    o = Outcome("dispatch", (a.id,), (Slot(f"reuse({a.id})"),))
    c = dataclasses.replace(c, acceptable=[*c.acceptable, o])
    assert _ctx_problems(_problems(c), a.id)


def test_rejected_when_id_is_a_unique_facts_key(base):
    c0, a = base
    c = dataclasses.replace(_with_context(c0, a), unique_facts={a.id: a.description.split()[0]})
    assert _ctx_problems(_problems(c), a.id)


def test_duplicate_context_ids_in_one_case_rejected(base):
    c0, a = base
    c = _with_context(c0, a)
    c = dataclasses.replace(c, context_agents=[a, a])
    assert any("context agent" in p and a.id in p and "duplicate" in p.lower() for p in _problems(c))


def test_same_context_id_defined_differently_in_two_cases_rejected(cases, base):
    c0, a = base
    c1 = next(c for c in cases if c.id != c0.id and c.ia_history)
    a2 = dataclasses.replace(a, description=a.description + " Different.")
    ps = _problems(_with_context(c0, a), _with_context(c1, a2))
    assert any(a.id in p and "defined differently" in p for p in ps)


def test_context_agent_does_not_count_as_required_for_outcome_checks(base):
    c0, a = base
    c = _with_context(c0, a)
    required_ids = {x.id for x in c.required_agents}
    assert a.id not in required_ids and c.context_agents == [a]


# ------------------------------------------------------------- 4. retrieval

def test_make_passes_context_agents_as_extra_agents(cases, world, base):
    c0, a = base
    c = _with_context(c0, a)
    q = re_mod._make(c, world, qid=c.id, group="frozen", message=c.message)
    assert q is not None and q.extra_agents == (a,)
    q0 = re_mod._make(c0, world, qid=c0.id, group="frozen", message=c0.message)
    assert q0.extra_agents == ()


def test_unrelated_history_donor_context_agents_are_loaded_as_extra(cases, world, base):
    _, a = base
    donor_id = re_mod.UNRELATED_DONORS[0]
    donors = {c.id: c for c in cases}
    donors[donor_id] = _with_context(donors[donor_id], a)
    new_cases = [donors.get(c.id, c) for c in cases]
    frozen = [q for q in re_mod.case_queries(new_cases, world, "dev") if q.group == "frozen"]
    out = re_mod.unrelated_history_variants(frozen, new_cases)
    assert out and any(a in q.extra_agents for q in out)
    for q in out:
        assert all(isinstance(x, AgentDef) for x in q.extra_agents)


# --------------------------------------------------------- 5. regrade dir

class _Captured(Exception):
    pass


def _fake_run(tmp_path, case_set):
    run = tmp_path / "run"
    run.mkdir()
    summary = {"case_ids": [], "modes": [], "sizes": []}
    if case_set is not None:
        summary["case_set"] = case_set
    (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return run


def _capture(monkeypatch):
    seen = []

    def fake(path, *a, **k):
        seen.append(Path(path))
        raise _Captured

    monkeypatch.setattr(run_store, "load_frozen_cases", fake)
    return seen


def test_regrade_uses_the_runs_recorded_absolute_case_dir(tmp_path, monkeypatch):
    seen = _capture(monkeypatch)
    other = tmp_path / "frozen_copy"
    run = _fake_run(tmp_path, {"dir": str(other), "version": "v9"})
    with pytest.raises(_Captured):
        run_store.regrade(run)
    assert seen == [other]


def test_regrade_resolves_a_relative_recorded_dir_against_the_repo_root(tmp_path, monkeypatch):
    seen = _capture(monkeypatch)
    target = tmp_path / "frozen_rel"
    rel = os.path.relpath(target, REPO)
    run = _fake_run(tmp_path, {"dir": rel})
    with pytest.raises(_Captured):
        run_store.regrade(run)
    assert seen[0].resolve() == target.resolve()


def test_regrade_explicit_cases_dir_wins(tmp_path, monkeypatch):
    seen = _capture(monkeypatch)
    run = _fake_run(tmp_path, {"dir": str(tmp_path / "recorded")})
    with pytest.raises(_Captured):
        run_store.regrade(run, cases_dir=tmp_path / "explicit")
    assert seen == [tmp_path / "explicit"]


def test_regrade_without_recorded_dir_falls_back_to_CASES_DIR(tmp_path, monkeypatch):
    seen = _capture(monkeypatch)
    run = _fake_run(tmp_path, {"version": "v1"})
    with pytest.raises(_Captured):
        run_store.regrade(run)
    assert seen == [caseset.CASES_DIR]


def test_cli_regrade_cases_dir_default_is_none(tmp_path, monkeypatch):
    run = _fake_run(tmp_path, {"dir": "x"})
    (run / "records.jsonl").write_text("")
    got = {}

    def fake(run_dir, **kw):
        got.update(kw)
        raise _Captured

    monkeypatch.setattr(run_store, "regrade", fake)
    with pytest.raises(_Captured):
        run_mod.main(["regrade", str(run)])
    assert got["cases_dir"] is None


# ---------------------------------------------------------- 6. CASES_DIR

def test_caseset_cases_dir_is_v2():
    assert caseset.CASES_DIR == caseset.V2_DIR


def test_every_module_reexports_the_one_cases_dir():
    from evals import routing_run
    from evals.world import dense
    for m in (run_mod, routing_run, run_store, re_mod, dense):
        assert m.CASES_DIR is caseset.CASES_DIR or m.CASES_DIR == caseset.CASES_DIR, m.__name__
    assert caseset.V1_DIR == V1


def test_build_cases_defaults_to_v1_even_if_cases_dir_is_switched(monkeypatch):
    import inspect
    monkeypatch.setattr(caseset, "CASES_DIR", REPO / "evals" / "cases" / "v2")
    assert inspect.signature(run_mod.build_cases).parameters["out_dir"].default == V1
    got = {}

    def fake(out_dir, **kw):
        got["out"] = Path(out_dir)
        raise _Captured

    monkeypatch.setattr(run_mod, "build_cases", fake)
    monkeypatch.setattr(run_mod, "is_frozen", lambda d: False)  # v1 is frozen; main would refuse before building
    with pytest.raises(_Captured):
        run_mod.main(["build-cases"])
    assert got["out"] == V1


def test_inspect_export_dataset_name_comes_from_the_run_summary(tmp_path):
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log
    from evals.inspect_export import export_run
    from tests.evals.synthetic_run import write_run
    run = write_run(tmp_path / "runs", [("case-a", "legacy", 10, 0, True, "dispatch", [], None)])
    s = json.loads((run / "summary.json").read_text())
    s["case_set"] = {**s.get("case_set", {}), "dir": "evals/cases/v2"}
    (run / "summary.json").write_text(json.dumps(s))
    p = next(iter(export_run(run, tmp_path / "logs")))
    assert read_eval_log(str(p)).eval.dataset.name == "evals/cases/v2"
