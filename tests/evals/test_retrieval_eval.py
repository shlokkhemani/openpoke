"""Task 12: the offline Layer-1 retrieval eval (``evals.retrieval_eval`` and ``evals.harness.load_world``).

Offline and free: ``HashingEmbedder`` only, ``FastEmbedder`` fails if built, all output under tmp_path.
Interface assumed by these tests (from the Task 12 design addendum):

- ``RQuery(id, case_id, group, kind, query, message, expected, required, referenced, outcome)``;
- ``expected_for(case, world) -> (kind, set)``; ``case_queries(cases, world, split)``;
  ``template_queries(world, examples, cases, n_template, first_seed) -> TemplateSet(queries, seeds, skipped_seeds)``;
  ``retrieval_queries(cases, world, split="dev", queries="all", n_template=300)``;
- Task 12b (one configuration, no ablations, no lowercase group):
  ``evaluate(queries, world, sizes, embedder, descriptions=None) -> {"cells", "rows", "skipped_n_below_required"}``,
  each cell a dict with group, kind, n, k, count, recall, all_found, person_cover, mean_len, mrr, trivial,
  extra_referenced (None except for the ``unrelated_history`` group); ``KS = (5, 10, 20)``;
  ``unrelated_history_variants(frozen, cases) -> list[RQuery]`` (group ``unrelated_history``, id ``<id>:unrelated``;
  donors ``UNRELATED_DONORS`` assigned round-robin over the sorted eligible queries; ``RQuery.extra_agents`` holds the
  donor's referenced agent, which is loaded into the store); ``_headline(result, split, sizes)``;
- metrics ``recall``, ``all_found``, ``mrr``, ``recall_at`` take ``ranked: list[list[str]]`` and
  ``expected: list[set[str]]``.
"""
import dataclasses
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pytest

from evals import retrieval_eval as re_mod
from evals import run as run_mod
from evals.caseset import V1_DIR, load_frozen_cases
from evals.clock import days_ago
from evals.harness.load_world import CachedEmbedder, load_into_store
from evals.retrieval_eval import (
    UNRELATED_DONORS, RQuery, _headline, all_found, case_queries, evaluate, expected_for, mrr, recall,
    recall_at, retrieval_queries, template_queries, unrelated_history_variants,
)
from evals.schema import AgentDef, Contact, Trigger, format_outcome, load_cases
from evals.world.generate import EXAMPLES, WORLD_PATH
from evals.world.roster import World, load_world
from server.services.agents.embeddings import HashingEmbedder
from server.services.agents.retrieval import RetrievalConfig, build_query
from server.services.agents.store import AgentStore

CASES_DIR = Path("evals/cases/v1")
KS = (5, 10, 20)


@pytest.fixture(autouse=True)
def _no_fastembed(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("FastEmbedder must not be built in tests")

    monkeypatch.setattr("server.services.agents.embeddings.FastEmbedder", boom)
    monkeypatch.setattr("evals.retrieval_eval.FastEmbedder", boom, raising=False)
    monkeypatch.setattr("evals.run.FastEmbedder", boom, raising=False)


@pytest.fixture(scope="module")
def world():
    return load_world(WORLD_PATH)


@pytest.fixture(scope="module")
def cases():
    return load_frozen_cases(CASES_DIR)


@pytest.fixture(scope="module")
def by_id(cases):
    return {c.id: c for c in cases}


@pytest.fixture(scope="module")
def examples():
    return load_cases(EXAMPLES)


def hashing():
    return CachedEmbedder(HashingEmbedder())


# 1 ----------------------------------------------------------------------------------------------
def test_recall_is_perfect_when_roster_is_only_the_required_agents(world, cases):
    queries = [q for q in case_queries(cases, world, "dev") if q.group == "frozen"]
    assert queries
    by_n = {}
    for q in queries:
        by_n.setdefault(len(q.required), []).append(q)
    for n, group in by_n.items():
        result = evaluate(group, world, [n], hashing())
        cells = [c for c in result["cells"] if c["k"] == 10]
        assert all("ablation" not in c for c in cells)
        assert sum(c["count"] for c in cells) == len(group)
        assert all(c["recall"] == 1.0 for c in cells), (n, [c for c in cells if c["recall"] != 1.0])


# 2 ----------------------------------------------------------------------------------------------
def test_metrics_math():
    assert mrr([["a", "b"]], [{"b"}]) == 0.5
    assert mrr([["a", "b"]], [{"z"}]) == 0.0
    assert mrr([["a", "b"], ["x", "y"]], [{"b"}, {"a"}]) == 0.25
    assert recall([["a"]], [{"a", "b"}]) == 0.5
    assert recall([["a", "b"], ["x"]], [{"a"}, {"y"}]) == 0.5
    assert all_found([["a", "b"], ["a"]], [{"a", "b"}, {"a", "b"}]) == 0.5
    with pytest.raises(ValueError):
        recall([["a"]], [set()])
    assert recall_at([["a", "b", "c"]], [{"c"}], 2) == 0.0
    assert recall_at([["a", "b", "c"]], [{"c"}], 3) == 1.0
    assert recall_at([["a", "b", "c"], ["c", "a", "b"]], [{"c", "a"}, {"c", "a"}], 1) == 0.5


# 3 ----------------------------------------------------------------------------------------------
def test_one_configuration_cells_per_group_kind_n_and_k(world, cases):
    queries = [q for q in case_queries(cases, world, "dev") if q.group == "frozen"]
    result = evaluate(queries, world, [10, 30], hashing())
    assert result["ks"] == [5, 10, 20]
    kinds = {(q.group, q.kind) for q in queries}
    seen = {(c["group"], c["kind"], c["n"], c["k"]) for c in result["cells"]}
    assert seen == {(g, kd, n, k) for g, kd in kinds for n in (10, 30) for k in KS}
    for c in result["cells"]:
        assert "ablation" not in c
        for key in ("recall", "all_found", "person_cover", "mean_len", "mrr", "count", "trivial", "extra_referenced"):
            assert key in c
        assert 0.0 <= c["recall"] <= 1.0 and 0.0 <= c["mrr"] <= 1.0
        assert c["trivial"] == (c["n"] <= c["k"])
    assert all("ablation" not in r for r in result["rows"])


# 4 ----------------------------------------------------------------------------------------------
def test_ablations_and_lowercase_variant_are_gone():
    import evals.retrieval_eval as m
    assert not hasattr(m, "ABLATIONS") and not hasattr(m, "lowercase_variant")


def test_mrr_is_on_the_full_fused_ranking_beyond_k(world):
    fillers = list(world.filler_order[:30])
    base = dict(case_id="c", group="frozen", kind="target", message="quarterly zebra", referenced=False,
                outcome="x", required=())
    result = None
    for target in fillers:
        q = RQuery(id="mrr-probe", query="quarterly zebra", expected={target}, **base)
        result = evaluate([q], world, [30], hashing(), ks=(5, 60))
        rank = next(r for r in result["rows"] if r["k"] == 60)["first_hit_rank"]
        if rank is not None and rank > 5:
            break
    else:
        pytest.fail("no filler ranked below 5")
    cells = {c["k"]: c for c in result["cells"]}
    assert cells[5]["recall"] == 0.0           # not in the top 5 ...
    assert cells[5]["mrr"] > 0.0               # ... yet MRR still sees it
    assert cells[5]["mrr"] == pytest.approx(1 / rank) == pytest.approx(cells[60]["mrr"])


def test_referenced_looks_only_at_the_last_exchange(world, cases):
    from evals.schema import Turn
    base = next(c for c in cases if c.id == "amb-person-006" and not any(t.agent_id for t in c.ia_history))
    old_ref = Turn(role="agent", text="old digest", agent_id="ag_stale_one")
    tail = [Turn(role="user", text="ok"), Turn(role="assistant", text="sure")]
    older = dataclasses.replace(base, ia_history=[old_ref, Turn(role="assistant", text="relayed"), *tail])
    last = dataclasses.replace(base, ia_history=[*tail[:1], Turn(role="agent", text="new", agent_id="ag_new_one"),
                                                 Turn(role="assistant", text="relayed")])
    rest = [c for c in cases if c.id != base.id]
    qs_old = case_queries([older, *rest], world, "dev")
    qs_last = case_queries([last, *rest], world, "dev")
    q_old = next(q for q in qs_old if q.group == "frozen" and q.case_id == base.id)
    q_last = next(q for q in qs_last if q.group == "frozen" and q.case_id == base.id)
    assert q_old.referenced is False and "ag_stale_one" not in q_old.query
    assert q_last.referenced is True and "ag_new_one" in q_last.query
    assert any(q.group == "unrelated_history" and q.case_id == base.id for q in qs_old)
    assert not any(q.group == "unrelated_history" and q.case_id == base.id for q in qs_last)


# 5 ----------------------------------------------------------------------------------------------
def test_expected_sets_by_outcome(world, by_id):
    def exp(cid):
        return expected_for(by_id[cid], world)

    chen_park = {"ag_chen_budget", "ag_park_dinner"}
    assert exp("amb-person-001") == ("both_candidates", chen_park)
    assert exp("amb-person-006") == ("both_candidates", {"ag_27trrgec", "ag_e544hlzo", "ag_vgbzlvg7"})
    assert exp("amb-person-005") == ("both_candidates", chen_park)  # pronoun case: fallback to agents with contacts
    assert exp("amb-person-002") == ("lookalikes", {"ag_chen_budget"})
    assert exp("amb-person-007") == ("target", {"ag_dcl3r2h4"})
    assert exp("broad-person-001") == ("set", {"ag_dana_repair", "ag_dana_lease", "ag_dana_parking"})
    assert exp("multi-intent-002") == ("set", {"ag_c6obzuoh"})
    assert exp("multi-person-003") == ("both_candidates", chen_park)
    kind, ids = exp("multi-person-002")
    assert kind == "lookalikes" and ids == {a.id for a in by_id["multi-person-002"].required_agents}
    assert exp("clear-person-002") == ("lookalikes", {"ag_m7s4pnzj"})
    assert exp("newtask-002") == ("lookalikes", {a.id for a in by_id["newtask-002"].required_agents})


# 6 ----------------------------------------------------------------------------------------------
def test_labelling_bugs_raise(world, by_id):
    case = by_id["amb-person-001"]
    bad = dataclasses.replace(case, clarify_should_name=["Alice Chen", "Nobody Here"])
    with pytest.raises(ValueError, match="Nobody Here"):
        expected_for(bad, world)

    fid = world.filler_order[0]
    twin = dataclasses.replace(world.agents[fid], contacts=(Contact("twin@example.com", "alice  CHEN", "to"),))
    polluted = dataclasses.replace(world, agents={**world.agents, fid: twin})
    with pytest.raises(ValueError, match="(?i)alice chen"):
        expected_for(case, polluted)


# 7 ----------------------------------------------------------------------------------------------
def test_query_contains_history_agent_ids_and_is_flagged_referenced(world, cases):
    qs = {q.case_id: q for q in case_queries(cases, world, "test") if q.group == "frozen"}
    q = qs["trigger-002"]
    assert "ag_nightly_digest" in q.query
    assert q.query == build_query(q.message, [(t.role, t.text, t.agent_id) for t in
                                              next(c for c in cases if c.id == "trigger-002").ia_history], 2)
    assert RetrievalConfig().history_turns == 2
    # an agent line older than the last exchange does not reach the query
    old = dataclasses.replace(next(c for c in cases if c.id == "trigger-002"))
    hist = [(t.role, t.text, t.agent_id) for t in old.ia_history]
    padded = [("agent", "stale", "ag_stale_one"), ("assistant", "stale reply")] + hist
    assert "ag_stale_one" not in build_query(q.message, padded, 2) and "ag_nightly_digest" in build_query(q.message, padded, 2)
    assert q.query.endswith("stop sending me these")
    assert q.referenced is True
    assert qs["amb-person-001"].referenced is False
    dev = {q.case_id for q in case_queries(cases, world, "dev") if q.referenced and q.group == "frozen"}
    assert {"trigger-006", "amb-person-007"} <= dev


# 8 ----------------------------------------------------------------------------------------------
def test_template_queries_are_deterministic_unique_and_clean(world, cases, examples):
    a = template_queries(world, examples, cases, n_template=40, first_seed=100)
    b = template_queries(world, examples, cases, n_template=40, first_seed=100)
    assert [(q.id, q.query) for q in a.queries] == [(q.id, q.query) for q in b.queries]
    assert a.seeds == b.seeds and a.seeds[0] == 100
    assert a.seeds == list(range(100, 100 + len(a.seeds)))
    assert len(a.queries) >= 40
    ids = [q.id for q in a.queries]
    assert len(set(ids)) == len(ids)
    assert all(re.match(r"t\d+:", i) for i in ids)
    assert {q.group for q in a.queries} == {"template"}
    messages = [q.message for q in a.queries]
    assert len(set(messages)) == len(messages)
    frozen_msgs = {c.message for c in cases} | {c.original_message for c in cases if c.original_message}
    assert not frozen_msgs & set(messages)
    test_keys = {(frozenset(x.id for x in c.required_agents), format_outcome(c.acceptable[0]))
                 for c in cases if c.split == "test"}
    assert not any((frozenset(x.id for x in q.required), q.outcome) in test_keys for q in a.queries)


# 9 ----------------------------------------------------------------------------------------------
def test_a_failing_seed_is_skipped_and_listed(world, cases, examples, monkeypatch):
    real = re_mod.expand

    def flaky(w, ex, seed):
        if seed == 100:
            raise ValueError("boom")
        return real(w, ex, seed)

    monkeypatch.setattr(re_mod, "expand", flaky)
    out = template_queries(world, examples, cases, n_template=40, first_seed=100)
    assert out.skipped_seeds == [100]
    assert 100 not in out.seeds and out.seeds[0] == 101
    assert out.queries and not any(q.id.startswith("t100:") for q in out.queries)


# 10 ---------------------------------------------------------------------------------------------
def _hist(case):
    return [(t.role, t.text, t.agent_id) for t in case.ia_history]


def test_unrelated_history_group_is_last_exchange_plus_message_with_same_expected_set(world, cases, by_id):
    qs = case_queries(cases, world, "dev")
    frozen = {q.case_id: q for q in qs if q.group == "frozen"}
    ur = [q for q in qs if q.group == "unrelated_history"]
    # no dev case is history-less, so "unrelated" = own history references no agent id (donors excluded)
    eligible = {q.case_id for q in frozen.values() if not q.referenced and q.case_id not in UNRELATED_DONORS}
    assert ur and {q.case_id for q in ur} == eligible
    assert UNRELATED_DONORS == ("trigger-006", "amb-person-007")
    donor_ids = {"ag_ohyhhbka", "ag_dcl3r2h4"}
    for q in ur:
        base = frozen[q.case_id]
        assert q.id == f"{base.id}:unrelated" and q.group == "unrelated_history"
        assert q.message == base.message and q.kind == base.kind
        assert q.expected == base.expected and q.required == base.required and q.outcome == base.outcome
        donors = [by_id[d] for d in UNRELATED_DONORS]
        assert q.query in {build_query(base.message, _hist(d), 2) for d in donors}
        assert q.query.endswith(base.message)
        own = base.query[: len(base.query) - len(base.message)]
        assert own and own not in q.query  # the query's own history text is absent
        assert any(i in q.query for i in donor_ids)
        assert q.referenced is True
        assert {a.id for a in q.extra_agents} <= donor_ids and q.extra_agents


def test_unrelated_history_pairing_is_fixed_round_robin_and_deterministic(world, cases, by_id):
    frozen = [q for q in case_queries(cases, world, "dev") if q.group == "frozen"]
    a = unrelated_history_variants(frozen, cases)
    b = unrelated_history_variants(list(reversed(frozen)), cases)
    assert [(q.id, q.query) for q in a] == [(q.id, q.query) for q in b]
    ordered = sorted(a, key=lambda q: q.case_id)
    for i, q in enumerate(ordered):
        donor = by_id[UNRELATED_DONORS[i % len(UNRELATED_DONORS)]]
        assert q.query == build_query(q.message, _hist(donor), 2), q.id


def test_unrelated_history_reports_recall_and_extra_referenced(world, cases):
    qs = [q for q in case_queries(cases, world, "dev") if q.group in ("frozen", "unrelated_history")]
    result = evaluate(qs, world, [10, 30], hashing())
    ur = [c for c in result["cells"] if c["group"] == "unrelated_history"]
    assert ur
    for c in ur:
        assert c["extra_referenced"] == 1.0  # the donor's agent is in the roster, so its id is forced in
        assert 0.0 <= c["recall"] <= 1.0
    assert all(c["extra_referenced"] is None for c in result["cells"] if c["group"] == "frozen")
    row = next(r for r in result["rows"] if r["group"] == "unrelated_history")
    assert any("referenced" in x["reasons"] and x["id"] not in row["expected"] for x in row["returned"])


# 11 ---------------------------------------------------------------------------------------------
def test_load_into_store(tmp_path):
    a1 = AgentDef(
        id="ag_t1", name="Digest", description="original text",
        contacts=(Contact("Alice.Chen@Example.COM", "Alice Chen", "to"),),
        triggers=(Trigger("daily at 8am", "send the zebra digest", "active"),
                  Trigger("weekly", "paused xyzzy payload", "paused")),
        last_user_activity_days_ago=3, last_run_days_ago=5)
    a2 = AgentDef(id="ag_t2", name="Other", description="plain agent")
    store = AgentStore(tmp_path / "agents.db")
    assert load_into_store([a1, a2], World(), store, hashing(), {"ag_t1": "overridden words"}) is None
    assert [c.email for c in store.contacts_for("ag_t1")] == ["alice.chen@example.com"]
    assert [a for a, _ in store.fts_search("zebra", 10)] == ["ag_t1"]
    assert store.fts_search("xyzzy", 10) == []
    assert [a for a, _ in store.fts_search("overridden", 10)] == ["ag_t1"]
    assert store.get("ag_t1").description == "overridden words"
    assert store.get("ag_t2").description == "plain agent"
    r1, r2 = store.get("ag_t1"), store.get("ag_t2")
    assert r1.last_user_activity_at == days_ago(3) and r1.last_run_at == days_ago(5)
    assert r2.last_user_activity_at == days_ago(0) and r2.last_run_at is None
    ids, mat = store.embeddings()
    assert set(ids) == {"ag_t1", "ag_t2"} and mat.shape[0] == 2


# 12 ---------------------------------------------------------------------------------------------
def test_embedding_cache_embeds_each_distinct_text_once():
    class Counting:
        def __init__(self):
            self.calls = []
            self.inner = HashingEmbedder()

        def embed(self, texts):
            self.calls.append(list(texts))
            return self.inner.embed(texts)

    inner = Counting()
    cached = CachedEmbedder(inner)
    out = cached.embed(["a b", "c d", "a b"])
    assert out.shape[0] == 3 and np.array_equal(out[0], out[2])
    assert inner.calls == [["a b", "c d"]]
    again = cached.embed(["c d", "e f"])
    assert inner.calls == [["a b", "c d"], ["e f"]]
    assert np.array_equal(again[0], out[1])
    cached.embed(["a b", "e f"])
    assert len(inner.calls) == 2


# 13 ---------------------------------------------------------------------------------------------
def test_a_grown_store_matches_a_fresh_one(world, cases):
    queries = [q for q in case_queries(cases, world, "dev") if q.group == "frozen"][:6]
    grown = evaluate(queries, world, [10, 30], hashing())
    fresh = evaluate(queries, world, [30], hashing())

    def at30(res, key):
        return [x for x in res[key] if x["n"] == 30]

    assert at30(grown, "cells") == at30(fresh, "cells")
    assert at30(grown, "rows") == at30(fresh, "rows")
    assert at30(fresh, "rows")


# 14 ---------------------------------------------------------------------------------------------
def test_broad_person_query_returns_the_answer_set_at_k20_without_expansion(world, cases):
    q = next(q for q in case_queries(cases, world, "test") if q.group == "frozen" and q.case_id == "broad-person-001")
    assert q.kind == "set" and len(q.expected) == 3
    result = evaluate([q], world, [30], hashing())
    cell = next(c for c in result["cells"] if c["k"] == 20 and c["kind"] == "set")
    assert cell["recall"] == 1.0
    reasons = {r for row in result["rows"] for x in row["returned"] for r in x["reasons"]}
    assert reasons <= {"bm25", "embedding", "referenced"}
    assert not {"person_expansion", "contact", "trigger"} & reasons


def test_headline_is_dev_frozen_recall_at_20_with_person_cover_for_both_candidates():
    def cell(kind, n, **kw):
        base = dict(group="frozen", kind=kind, n=n, k=20, count=2, recall=0.0, person_cover=None)
        return {**base, **kw}

    result = {"cells": [
        cell("target", 10, recall=0.5), cell("set", 10, recall=1.0),
        cell("both_candidates", 10, recall=0.0, person_cover=1.0),
        cell("lookalikes", 10, recall=0.0),                         # excluded
        cell("target", 10, k=5, recall=0.0),                         # wrong K
        cell("target", 10, group="template", recall=0.0),            # wrong group
        cell("target", 30, recall=0.0), cell("both_candidates", 30, person_cover=0.5),
    ]}
    # N=10: (0.5*2 + 1.0*2 + 1.0*2) / 6 ; N=30: (0*2 + 0.5*2) / 4
    assert _headline(result, "dev", [10, 30]) == "dev recall@20 (rrf) at N=10/30: 0.83/0.25"


# 15 ---------------------------------------------------------------------------------------------
def test_default_split_excludes_test_cases_and_their_variants(world, cases):
    test_ids = {c.id for c in cases if c.split == "test"}
    dev_ids = {c.id for c in cases if c.split == "dev"}
    default = retrieval_queries(cases, world, queries="frozen")
    assert {q.group for q in default} == {"frozen", "original", "unrelated_history"}
    assert {q.case_id for q in default} <= dev_ids
    assert {q.case_id for q in default if q.group == "frozen"} == dev_ids
    originals = {c.id for c in cases if c.split == "dev" and c.original_message}
    assert {q.case_id for q in default if q.group == "original"} == originals
    explicit = retrieval_queries(cases, world, split="test", queries="frozen")
    assert {q.case_id for q in explicit} <= test_ids and explicit


# 16 ---------------------------------------------------------------------------------------------
def test_n_below_the_required_count_is_skipped_and_counted(world, cases):
    q = next(q for q in case_queries(cases, world, "dev") if q.group == "frozen" and q.case_id == "amb-person-006")
    assert len(q.required) == 3
    result = evaluate([q], world, [2, 10], hashing())
    assert result["skipped_n_below_required"] == 1
    assert {c["n"] for c in result["cells"]} == {10}
    assert {r["n"] for r in result["rows"]} == {10}


# 17 ---------------------------------------------------------------------------------------------
def test_cli_writes_only_to_its_run_directory(world, cases, tmp_path, monkeypatch):
    # the CLI has no cases-dir flag; pin retrieval_eval.run's keyword default to the v1 set this test checks
    monkeypatch.setitem(re_mod.run.__kwdefaults__, "cases_dir", V1_DIR)
    out, exp = tmp_path / "results", tmp_path / "EXPERIMENTS.md"
    data_dir = Path("server/data")
    before = sorted(p.name for p in data_dir.glob("*")) if data_dir.exists() else []
    rc = run_mod.main(["retrieval", "--split", "dev", "--sizes", "10,30", "--embedder", "hashing",
                       "--descriptions", "world", "--queries", "frozen", "--purpose", "unit test run",
                       "--out-root", str(out), "--experiments", str(exp)])
    assert rc == 0
    assert (sorted(p.name for p in data_dir.glob("*")) if data_dir.exists() else []) == before
    (run_dir,) = [p for p in out.iterdir()]
    assert sorted(p.name for p in run_dir.iterdir()) == ["queries.jsonl", "report.md", "retrieval.json", "summary.json"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["EXPERIMENTS.md", "results"]

    data = json.loads((run_dir / "retrieval.json").read_text())
    assert {"config", "cells", "skipped_n_below_required"} <= set(data)
    assert data["config"] == dataclasses.asdict(RetrievalConfig())
    assert set(data["config"]) == {"k", "rrf_k", "history_turns"}
    assert all("ablation" not in c for c in data["cells"])
    summary = json.loads((run_dir / "summary.json").read_text())
    for key in ("purpose", "command", "git", "case_set_sha256", "descriptions", "embedder", "seeds", "counts",
                "timings"):
        assert key in summary
    assert summary["purpose"] == "unit test run" and summary["embedder"] == "hashing"

    n_queries = len(retrieval_queries(cases, world, split="dev", queries="frozen"))
    rows = [json.loads(line) for line in (run_dir / "queries.jsonl").read_text().splitlines()]
    assert len(rows) == n_queries * 2 * len(KS)
    assert {"expected", "returned", "first_hit_rank", "n", "k"} <= set(rows[0]) and "ablation" not in rows[0]

    report = (run_dir / "report.md").read_text()
    assert "recall@20" in report and "unrelated_history" in report
    for gone in ("rrf_boosts", "person expansion", "Person expansion", "lowercase", "ablation"):
        assert gone not in report, gone

    lines = exp.read_text().splitlines()
    row = [line for line in lines if run_dir.name in line]
    assert len(row) == 1 and "$0 (offline)" in row[0]
    assert "dev recall@20 (rrf) at N=10/30" in row[0]


# ======================= Task 12c: name-overlap baseline, dense world in the CLI =====================


def _toy(i, name, contact=None):
    contacts = (Contact(f"{contact.split()[0].lower()}@x.io", contact, "to"),) if contact else ()
    return AgentDef(i, name, "unused description words", contacts)


def test_name_overlap_rank_puts_name_word_matches_first_and_returns_everyone():
    agents = [_toy("ag_a", "Quarterly zebra digest"), _toy("ag_b", "Gardening plan"),
              _toy("ag_c", "Weekly report", "Mira Tanaka"), _toy("ag_d", "Plumbing zebra gardening")]
    ranked = re_mod.name_overlap_rank(agents, "did mira send the gardening zebra plumbing note", "q1")
    assert sorted(ranked) == ["ag_a", "ag_b", "ag_c", "ag_d"]
    assert ranked[0] == "ag_d"                       # three shared words
    assert set(ranked[1:]) == {"ag_a", "ag_b", "ag_c"}   # one shared word each (zebra / gardening / mira)
    only_contact = re_mod.name_overlap_rank(agents, "mira", "q1")
    assert only_contact[0] == "ag_c"


def test_name_overlap_rank_counts_distinct_words_and_ignores_stopwords():
    agents = [_toy("ag_a", "Zebra"), _toy("ag_b", "Zebra gardening")]
    assert re_mod.name_overlap_rank(agents, "zebra zebra zebra gardening", "k")[0] == "ag_b"
    # stopwords alone score nothing: everyone ties, order comes from the seeded RNG
    agents = [_toy("ag_a", "About the"), _toy("ag_b", "Of and to"), _toy("ag_c", "Zebra")]
    assert re_mod.name_overlap_rank(agents, "about the of and to", "k") == re_mod.name_overlap_rank(agents, "about the of and to", "k")
    assert re_mod.name_overlap_rank(agents, "zebra about", "k")[0] == "ag_c"


def test_name_overlap_rank_is_deterministic_and_ties_depend_only_on_seed_key():
    agents = [_toy(f"ag_{i}", f"Thing{i} item") for i in range(12)]
    a = re_mod.name_overlap_rank(agents, "nothing matches here", "q-1")
    assert a == re_mod.name_overlap_rank(agents, "nothing matches here", "q-1")
    assert sorted(a) == sorted(x.id for x in agents)
    assert any(re_mod.name_overlap_rank(agents, "nothing matches here", f"q-{k}") != a for k in range(2, 8))


OLD_CELLS = {  # captured from the pre-12c implementation: (kind, n, k) -> (count, recall, all_found, mrr)
    ("both_candidates", 10, 5): (1, 1.0, 1.0, 1.0), ("set", 10, 5): (2, 1.0, 1.0, 1.0),
    ("set", 30, 5): (2, 1.0, 1.0, 1.0),
    ("target", 10, 5): (2, 1.0, 1.0, 0.75), ("target", 10, 10): (2, 1.0, 1.0, 0.75), ("target", 10, 20): (2, 1.0, 1.0, 0.75),
    ("target", 30, 5): (2, 1.0, 1.0, 0.625), ("target", 30, 10): (2, 1.0, 1.0, 0.625), ("target", 30, 20): (2, 1.0, 1.0, 0.625),
}
OLD_COUNTS = {"both_candidates": 1, "lookalikes": 1, "set": 2, "target": 2}


def _fixed_small_result(world, cases):
    qs = [q for q in case_queries(cases, world, "dev") if q.group == "frozen"][:6]
    assert [q.id for q in qs] == ["amb-person-006", "amb-person-007", "broad-person-005", "broad-person-006",
                                  "clear-person-005", "clear-person-006"]
    return qs, evaluate(qs, world, [10, 30], hashing())


def test_existing_cell_values_are_unchanged_and_baseline_is_added(world, cases):
    _, result = _fixed_small_result(world, cases)
    assert len(result["cells"]) == 24
    for c in result["cells"]:
        want = OLD_CELLS.get((c["kind"], c["n"], c["k"]), (OLD_COUNTS[c["kind"]], 1.0, 1.0, 1.0))
        got = (c["count"], round(c["recall"], 6), round(c["all_found"], 6), round(c["mrr"], 6))
        assert got == want, (c["kind"], c["n"], c["k"], got)
        assert "baseline" in c and 0.0 <= c["baseline"] <= 1.0
        if c["trivial"]:
            assert c["baseline"] == 1.0              # N <= K: everyone is in the top K
    assert all("baseline_recall" in r for r in result["rows"])


def test_baseline_is_the_recall_of_name_overlap_rank_over_the_store_at_this_n(world, cases, monkeypatch):
    q = next(q for q in case_queries(cases, world, "dev") if q.group == "frozen" and q.kind == "target")
    seen = []

    def fake_rank(agents, query, seed_key):
        seen.append((len(list(agents)), query, seed_key))
        return [a.id for a in agents if a.id not in q.expected] + sorted(q.expected)   # expected ranked last

    monkeypatch.setattr(re_mod, "name_overlap_rank", fake_rank)
    result = evaluate([q], world, [30], hashing())
    assert seen and all(n == 30 and query == q.query and key == q.id for n, query, key in seen)
    cell = {c["k"]: c for c in result["cells"]}
    assert all(cell[k]["baseline"] == 0.0 for k in KS)           # last of 30: outside every K <= 20
    monkeypatch.setattr(re_mod, "name_overlap_rank", lambda agents, query, seed_key: sorted(q.expected) + [
        a.id for a in agents if a.id not in q.expected])
    cell = {c["k"]: c for c in evaluate([q], world, [30], hashing())["cells"]}
    assert all(cell[k]["baseline"] == 1.0 for k in KS)


def test_base_run_report_has_base_at_20_right_after_recall_at_20(world, cases, tmp_path):
    out, exp = tmp_path / "results", tmp_path / "EXPERIMENTS.md"
    rc = run_mod.main(["retrieval", "--split", "dev", "--sizes", "10,30", "--embedder", "hashing",
                       "--descriptions", "world", "--queries", "frozen", "--world", "base",
                       "--out-root", str(out), "--experiments", str(exp)])
    assert rc == 0
    (run_dir,) = list(out.iterdir())
    report = (run_dir / "report.md").read_text()
    assert "| recall@5 | recall@10 | recall@20 | base@20 | all_found@20 |" in report
    assert re.search(r"^- dev recall@20 \(rrf\) at N=10/30: [\d.]+/[\d.]+$", report, re.M)
    cells = json.loads((run_dir / "retrieval.json").read_text())["cells"]
    assert all("baseline" in c for c in cells)
    assert "dense" not in (run_dir / "summary.json").read_text().split('"queries"')[0].lower()


# ---- dense run -------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def dense_world(world):
    from evals.world.dense import build_dense_world
    return build_dense_world(world)


def _write_paras(path, dense):
    path.write_text(json.dumps({"model": "m", "items": {t: f"zzq{i:02d} wobble" for i, t in enumerate(dense.topics)},
                                "dropped": [], "errors": [], "skipped_budget": []}), encoding="utf-8")


def _dense_run(tmp_path, dense, sizes=(100,), split="dev", limit=2, **kw):
    paras = tmp_path / "dense_paraphrases.json"
    if not paras.exists():
        _write_paras(paras, dense)
    out, exp = tmp_path / "results", tmp_path / "EXPERIMENTS.md"
    rc = re_mod.run(split=split, sizes=list(sizes), embedder_name="hashing", descriptions_source="regen",
                    queries="all", purpose="retrieval-dense", command="python -m evals.run retrieval --world dense",
                    out_root=out, experiments=exp, world_kind="dense", paraphrases_path=paras,
                    dense_topic_limit=limit, **kw)
    return rc, out, exp, paras


def test_dense_cli_writes_report_with_base_column_and_one_experiments_line(dense_world, tmp_path):
    rc, out, exp, paras = _dense_run(tmp_path, dense_world)
    assert rc == 0
    (run_dir,) = list(out.iterdir())
    assert sorted(p.name for p in run_dir.iterdir()) == ["queries.jsonl", "report.md", "retrieval.json", "summary.json"]
    report = (run_dir / "report.md").read_text()
    assert "base@20" in report and "median" in report.lower()
    for kind in ("target_exact", "target_para", "topic_noname", "history_pull"):
        assert kind in report
    pat = r"dense dev target_para recall@20 at N=100: \d\.\d\d \(base@20 \d\.\d\d\)"
    assert re.search(pat, report)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["descriptions"]["source"] == "world (forced for dense)"
    assert summary["paraphrases"]["sha256"] == hashlib.sha256(paras.read_bytes()).hexdigest()
    assert {"dropped_at_load", "skipped_topics"} <= set(summary["paraphrases"])
    assert summary["counts"]["dense"] == 14 and summary["split"] == "dev"
    lines = [ln for ln in exp.read_text().splitlines() if run_dir.name in ln]
    assert len(lines) == 1 and re.search(pat, lines[0]) and "retrieval-dense" in lines[0]
    rows = [json.loads(ln) for ln in (run_dir / "queries.jsonl").read_text().splitlines()]
    assert rows and all(isinstance(r["full_first_hit_rank"], int) and r["full_first_hit_rank"] >= 1 for r in rows)
    assert {"baseline_recall", "first_hit_rank", "expected", "returned"} <= set(rows[0])
    data = json.loads((run_dir / "retrieval.json").read_text())
    assert {c["group"] for c in data["cells"]} == {"dense"} and {c["n"] for c in data["cells"]} == {100}


def test_dense_run_skips_sizes_below_96_and_counts_them(dense_world, tmp_path):
    rc, out, _, _ = _dense_run(tmp_path, dense_world, sizes=(50, 100))
    assert rc == 0
    (run_dir,) = list(out.iterdir())
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["counts"]["skipped_n_below_required"] == 14
    assert {c["n"] for c in json.loads((run_dir / "retrieval.json").read_text())["cells"]} == {100}


def test_dense_run_refuses_without_the_paraphrase_file(tmp_path, capsys):
    out = tmp_path / "results"
    rc = re_mod.run(split="dev", sizes=[100], embedder_name="hashing", descriptions_source="world", queries="all",
                    purpose="", command="x", out_root=out, experiments=tmp_path / "E.md", world_kind="dense",
                    paraphrases_path=tmp_path / "missing.json", dense_topic_limit=2)
    assert rc == 1 and "dense_paraphrases" in capsys.readouterr().out.replace("missing", "dense_paraphrases")
    assert not out.exists() or not list(out.iterdir())
    rc = run_mod.main(["retrieval", "--world", "dense", "--sizes", "100", "--paraphrases",
                       str(tmp_path / "missing.json"), "--out-root", str(out), "--experiments", str(tmp_path / "E.md")])
    assert rc == 1


def test_dense_run_drops_paraphrases_that_leak_at_load(dense_world, tmp_path):
    paras = tmp_path / "dense_paraphrases.json"
    items = {t: f"zzq{i:02d} wobble" for i, t in enumerate(dense_world.topics)}
    from evals.world.dense import split_topics
    leaky = split_topics(dense_world)["dev"][0]
    items[leaky] = dense_world.topic_meta[leaky].short
    paras.write_text(json.dumps({"items": items}), encoding="utf-8")
    rc, out, _, _ = _dense_run(tmp_path, dense_world, limit=None)
    assert rc == 0
    (run_dir,) = list(out.iterdir())
    summary = json.loads((run_dir / "summary.json").read_text())
    assert [d["topic"] for d in summary["paraphrases"]["dropped_at_load"]] == [leaky]


def test_dense_run_does_not_touch_server_data_or_the_world(world, dense_world, tmp_path):
    data_dir = Path("server/data")
    before = sorted(p.name for p in data_dir.glob("*")) if data_dir.exists() else []
    sha = hashlib.sha256(WORLD_PATH.read_bytes()).hexdigest()
    rc, *_ = _dense_run(tmp_path, dense_world)
    assert rc == 0 and hashlib.sha256(WORLD_PATH.read_bytes()).hexdigest() == sha
    assert (sorted(p.name for p in data_dir.glob("*")) if data_dir.exists() else []) == before


def test_evaluate_on_dense_queries_adds_full_first_hit_rank(world, dense_world):
    from evals.world.dense import dense_queries
    paras = {t: f"zzq{i:02d} wobble" for i, t in enumerate(dense_world.topics)}
    qs = dense_queries(dense_world, paras, "dev")[:5]
    result = evaluate(qs, world, [100], hashing(), descriptions={})
    assert result["rows"] and all(isinstance(r["full_first_hit_rank"], int) for r in result["rows"])
    assert result["skipped_n_below_required"] == 0


# Task 16f -----------------------------------------------------------------------------------------
def test_evaluate_passes_the_message_to_every_search(world, monkeypatch):
    seen = []
    real = re_mod.search_agents

    def spy(*args, **kwargs):
        seen.append(kwargs.get("message"))
        return real(*args, **kwargs)

    monkeypatch.setattr(re_mod, "search_agents", spy)
    fillers = list(world.filler_order[:30])
    q = RQuery(id="msg-probe", case_id="c", group="frozen", kind="target", query="history words\nquarterly zebra",
               message="quarterly zebra", expected={fillers[0]}, referenced=False, outcome="x", required=())
    evaluate([q], world, [30], hashing(), ks=(5, 20))
    assert seen and all(m == "quarterly zebra" for m in seen)
