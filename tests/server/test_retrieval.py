import dataclasses
import os
from datetime import datetime, timedelta, timezone
import inspect

import numpy as np
import pytest

from server.config import Settings
from server.services.agents.embeddings import FastEmbedder, HashingEmbedder
from server.services.agents.index import refresh_search_index
from server.services.agents.retrieval import (
    Candidate,
    RetrievalConfig,
    build_query,
    rrf,
    search_agents,
)
from server.services.agents.store import AgentRecord, AgentStore, ContactRecord

N = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
OLD = N - timedelta(days=200)
CFG = RetrievalConfig()


def add(store, emb, agent_id, name, desc="", contacts=(), created=OLD, last_user=None):
    store.insert_agent(AgentRecord(agent_id, name, desc, created, last_user, None))
    if contacts:
        store.add_contacts(agent_id, [ContactRecord(e, n, "to") for e, n in contacts])
    refresh_search_index(store, agent_id, [], emb)


def ids(cands):
    return [c.agent_id for c in cands]


@pytest.fixture
def emb():
    return HashingEmbedder()


@pytest.fixture
def store(tmp_path, emb):
    s = AgentStore(tmp_path / "roster.db")
    dana = ("dana@acme.com", "Dana Whitfield")
    add(s, emb, "ag_dana_1", "Email Dana", "weekly sync notes with Dana", [dana])
    add(s, emb, "ag_dana_2", "Dana invoice follow-up", "chase the March invoice", [dana])
    add(s, emb, "ag_dana_3", "Dana contract", "contract renewal thread", [dana])
    add(s, emb, "ag_alice_chen", "Email Alice Chen", "budget thread with Alice",
        [("alice.chen@northwind.io", "Alice Chen")])
    add(s, emb, "ag_alice_park", "Email Alice Park", "design review with Alice",
        [("alice.park@northwind.io", "Alice Park")])
    add(s, emb, "ag_bob", "Email Bob", "lunch plans with Bob", [("bob@lee.org", "Bob Lee")])
    add(s, emb, "ag_priya_1", "Priya work", "standup with Priya", [("priya@acme.com", "Priya Raman")])
    add(s, emb, "ag_priya_2", "Priya personal", "weekend plans", [("p.raman@gmail.com", "Priya Raman")])
    add(s, emb, "ag_chen_budget", "Chen budget", "quarterly budget spreadsheet")
    add(s, emb, "ag_will", "Email Will", "hiring notes", [("will@varga.dev", "Will Varga")])
    add(s, emb, "ag_lex", "Invoice reminders", "quarterly invoice reminder digest")
    add(s, emb, "ag_zanzibar", "Travel", "zanzibar trip itinerary")
    for i in range(25):
        add(s, emb, f"ag_fill_{i:02d}", f"Filler {i}", f"misc automation number {i}")
    return s


@pytest.fixture
def empty_store(tmp_path):
    return AgentStore(tmp_path / "empty.db")


def mini(tmp_path, emb, specs):
    s = AgentStore(tmp_path / "mini.db")
    for spec in specs:
        add(s, emb, **spec)
    return s


# ---- rrf ----

def test_rrf_merges_by_rank():
    assert rrf([["a", "b"], ["b", "c"]], 60)[0] == "b"


def test_rrf_exact_order_and_ties():
    assert rrf([["a", "b"], ["b", "c"]], 60) == ["b", "a", "c"]  # b: 1/62+1/61 > a: 1/61 > c: 1/62
    assert rrf([["b"], ["a"]], 60) == ["a", "b"]  # equal scores tie-break by id
    assert rrf([], 60) == []
    assert rrf([[], ["x"]], 60) == ["x"]


def S(store, emb, query, k=20, cfg=CFG):
    """search_agents without ``now`` (Task 12b drops it)."""
    return search_agents(store, emb, query, k, cfg=cfg)


def _bm25_ranking(store, query):
    return [a for a, _ in store.fts_search(query, 1000)]


def _embedding_ranking(store, emb, query):
    qv = np.asarray(emb.embed([query])[0], dtype=np.float32)
    ids_, mat = store.embeddings(qv.shape[0])
    sims = mat @ qv
    order = sorted(range(len(ids_)), key=lambda i: (-float(sims[i]), ids_[i]))
    return [ids_[i] for i in order]


# ---- rankings ----

def test_rrf_score_via_search(store, emb):
    top = S(store, emb, "zanzibar", 1)[0]
    assert top.agent_id == "ag_zanzibar"
    assert top.score == pytest.approx(1 / 61 + 1 / 61)  # first in both rankings


def test_search_order_is_exactly_the_fused_rankings(store, emb):
    for q in ("Dana invoice", "zanzibar trip", "quarterly budget", "alice.park@northwind.io"):
        fused = rrf([_bm25_ranking(store, q), _embedding_ranking(store, emb, q)], CFG.rrf_k)
        for k in (3, 20):
            assert ids(S(store, emb, q, k)) == fused[:k], (q, k)


def test_bm25_finds_exact_email(store, emb):
    assert S(store, emb, "alice.park@northwind.io", 1)[0].agent_id == "ag_alice_park"


def test_contact_name_found_through_bm25_alone(store, emb):
    assert "ag_bob" in _bm25_ranking(store, "Bob Lee")[:1]
    got = S(store, emb, "Bob Lee", 3)
    assert got[0].agent_id == "ag_bob" and "bm25" in got[0].reasons
    assert all("contact" not in c.reasons for c in got)


@pytest.mark.skipif(os.environ.get("OPENPOKE_FASTEMBED_TESTS") != "1", reason="downloads a model")
def test_embeddings_find_paraphrase(tmp_path):
    e = FastEmbedder()
    s = mini(tmp_path, e, [
        dict(agent_id="ag_a", name="Budget", desc="send the monthly budget summary by email"),
        dict(agent_id="ag_b", name="Pets", desc="vet appointments for the dog"),
    ])
    assert "ag_a" in ids(S(s, e, "mail the monthly finances recap", 1))


def test_agent_without_index_rows_still_returned(tmp_path, emb):
    s = AgentStore(tmp_path / "x.db")
    add(s, emb, "ag_indexed", "Indexed", "hello")
    s.insert_agent(AgentRecord("ag_bare", "Bare", "", OLD, None, None))
    assert set(ids(S(s, emb, "hello", 5))) == {"ag_indexed", "ag_bare"}


def test_results_are_deterministic(store, emb):
    a = S(store, emb, "Dana invoice", 5)
    b = S(store, emb, "Dana invoice", 5)
    assert a == b and all(isinstance(c, Candidate) for c in a)


def test_no_capital_or_name_behaviour(store, emb):
    assert S(store, emb, "Did dana reply?") == S(store, emb, "Did Dana reply?")
    assert S(store, emb, "tell dana I'm late") == S(store, emb, "tell Dana I'm late")


def test_search_agents_has_no_trigger_or_now_parameters():
    params = inspect.signature(search_agents).parameters
    assert "active_trigger_ids" not in params
    assert "now" not in params
    assert list(params)[:4] == ["store", "embedder", "query", "k"] and "cfg" in params


# ---- referenced ----

def test_referenced_agent_id_appended_when_outside_top_k(store, emb):
    got = S(store, emb, "dana ag_chen_budget", 1)
    by_id = {c.agent_id: c for c in got}
    assert "referenced" in by_id["ag_chen_budget"].reasons
    assert ids(got)[-1] == "ag_chen_budget"


def test_referenced_id_already_present_is_not_duplicated(store, emb):
    got = S(store, emb, "zanzibar ag_zanzibar", 3)
    assert ids(got).count("ag_zanzibar") == 1
    assert "referenced" in {c.agent_id: c for c in got}["ag_zanzibar"].reasons


def test_unknown_referenced_id_ignored(store, emb):
    assert "ag_nope_123" not in ids(S(store, emb, "see ag_nope_123", 5))


def test_length_is_k_plus_referenced_outside_top_k(store, emb):
    q = "zanzibar ag_fill_03 ag_fill_04"
    got = ids(S(store, emb, q, 5))
    outside = [a for a in ("ag_fill_03", "ag_fill_04") if a not in got[:5]]
    assert len(got) == 5 + len(outside) and set(got[5:]) == set(outside)
    assert all("referenced" in c.reasons for c in S(store, emb, q, 5) if c.agent_id in outside)


def test_referenced_are_never_trimmed_or_capped(store, emb):
    refs = [f"ag_fill_{i:02d}" for i in range(10, 25)]
    got = ids(S(store, emb, "zanzibar " + " ".join(refs), 1))
    assert set(refs) <= set(got)


def test_orphan_rows_are_dropped(store, emb):
    store.add_contacts("ag_ghost", [ContactRecord("ghost@x.io", "Ghost Person", "to")])
    store.set_search_text("ag_ghost", "ghost zebra")
    got = ids(S(store, emb, "Ghost Person zebra ghost@x.io", 25))
    assert "ag_ghost" not in got


# ---- k, small rosters, hostile input ----

def test_k_capped_and_small_roster(store, empty_store, emb):
    assert len(S(store, emb, "x", k=100)) == 37
    assert S(empty_store, emb, "x", 5) == []


def test_roster_smaller_than_k_returns_everything(tmp_path, emb):
    s = mini(tmp_path, emb, [dict(agent_id="ag_a", name="A"), dict(agent_id="ag_b", name="B")])
    assert set(ids(S(s, emb, "unrelated", 5))) == {"ag_a", "ag_b"}


@pytest.mark.parametrize("q", [
    "José", "O'Brien", "AND OR NOT", '"', "*", "-x", "a:b", "NEAR(", "", "   ", "\U0001F600",
])
def test_query_with_fts_operators_does_not_raise(store, emb, q):
    assert isinstance(S(store, emb, q, 5), list)


# ---- embedder, build_query, config ----

def test_hashing_embedder_deterministic_normalised_shapes():
    e = HashingEmbedder()
    v = e.embed(["hello world", "hello world", "something else", ""])
    assert v.shape == (4, 256)
    assert np.array_equal(v[0], v[1]) and np.array_equal(v, HashingEmbedder().embed(
        ["hello world", "hello world", "something else", ""]))
    assert np.allclose(np.linalg.norm(v[:3], axis=1), 1.0)
    assert not v[3].any()
    assert HashingEmbedder(dim=64).embed(["a"]).shape == (1, 64)


def test_build_query_uses_last_turns_with_agent_ids():
    hist = [("user", "old"), ("agent", "sent it", "ag_x"), ("user", "thanks")]
    assert build_query("did she reply", hist, 2) == "ag_x sent it\nthanks\ndid she reply"
    assert build_query("hi", hist, 0) == "hi"
    assert build_query("hi", [("user", "a"), ("assistant", "b")], 4) == "a\nb\nhi"


def test_build_query_last_exchange_only_drops_ids_in_older_turns():
    hist = [("agent", "old digest", "ag_old"), ("assistant", "told you"), ("user", "ok"),
            ("agent", "fresh news", "ag_new"), ("assistant", "relayed")]
    q = build_query("what now", hist, 2)
    assert "ag_old" not in q and "ag_new" in q and "old digest" not in q
    q3 = build_query("what now", hist, 5)
    assert "ag_old" in q3


def test_retrieval_config_defaults_and_from_settings():
    assert RetrievalConfig() == RetrievalConfig(k=20, rrf_k=60, history_turns=2)
    assert [f.name for f in dataclasses.fields(RetrievalConfig)] == ["k", "rrf_k", "history_turns"]
    assert RetrievalConfig.from_settings(Settings()) == RetrievalConfig()
    assert sorted(n for n in Settings.model_fields if n.startswith("retrieval_")) == [
        "retrieval_history_turns", "retrieval_k", "retrieval_rrf_k"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        CFG.k = 9


# ---- reasons ----

def _labels(tmp_path, emb, query, k=1):
    s = mini(tmp_path, emb, [
        dict(agent_id="ag_a", name="Alpha", desc="apple apple apple"),
        dict(agent_id="ag_b", name="Bravo", desc="apple"),
        dict(agent_id="ag_c", name="Charlie", desc="apple"),
    ])
    got = S(s, emb, query, k)
    return {c.agent_id: c.reasons for c in got}


def test_ranking_reasons_only_for_top_k(tmp_path, emb):
    got = _labels(tmp_path, emb, "apple ag_c")
    assert list(got)[0] == "ag_a" and "bm25" in got["ag_a"] and "embedding" in got["ag_a"]
    assert "bm25" not in got["ag_c"] and "embedding" not in got["ag_c"]  # only referenced, outside the top k
    assert got["ag_c"] == ["referenced"]


def test_reasons_follow_result_size(tmp_path, emb):
    s = mini(tmp_path, emb, [
        dict(agent_id="ag_a", name="Alpha", desc="apple apple apple"),
        dict(agent_id="ag_b", name="Bravo", desc="apple apple"),
        dict(agent_id="ag_c", name="Charlie", desc="apple"),
    ])
    got = {c.agent_id: c.reasons for c in S(s, emb, "apple ag_c", 2)}
    assert "bm25" in got["ag_a"] and "bm25" in got["ag_b"] and "bm25" not in got["ag_c"]
    assert "embedding" not in got["ag_c"]


def test_search_ignores_embeddings_of_other_size(tmp_path, emb):
    s = mini(tmp_path, emb, [
        dict(agent_id="ag_a", name="A", desc="apple"),
        dict(agent_id="ag_b", name="B", desc="banana"),
    ])
    s.set_embedding("ag_b", np.ones(7, dtype=np.float32))
    got = S(s, emb, "apple", 2)
    assert ids(got)[0] == "ag_a" and "embedding" in got[0].reasons
    assert "embedding" not in got[1].reasons


def test_fastembedder_empty_list_does_not_load_model(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def guarded(name, *a, **kw):
        if name == "fastembed":
            raise AssertionError("model loader called for an empty list")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", guarded)
    out = FastEmbedder().embed([])
    assert out.shape == (0, 384) and out.dtype == np.float32


# ---- embedder=None: BM25 only (Task 13-I) ----

def test_embedder_none_runs_bm25_only_with_no_embedding_reasons(store):
    cands = search_agents(store, None, "zanzibar", 5, cfg=CFG)
    assert cands[0].agent_id == "ag_zanzibar"
    assert cands[0].reasons == ["bm25"]
    assert all("embedding" not in c.reasons for c in cands)


def test_embedder_none_ranks_like_the_bm25_ranking(store):
    cands = search_agents(store, None, "quarterly invoice", 20, cfg=CFG)
    bm25 = _bm25_ranking(store, "quarterly invoice")
    assert ids(cands)[: len(bm25[:20])] == bm25[:20]


def test_embedder_none_still_keeps_referenced_ids(store):
    cands = search_agents(store, None, "ag_bob please", 1, cfg=CFG)
    assert "ag_bob" in ids(cands)
    assert "referenced" in next(c for c in cands if c.agent_id == "ag_bob").reasons


# ---- Task 16f: rankings also run on the message (A3) ----

def _sig(cands):
    return [(c.agent_id, c.score, tuple(c.reasons)) for c in cands]


@pytest.mark.parametrize("which", ["none", "same"])
def test_no_message_or_message_equal_to_query_changes_nothing(store, emb, which):
    query = "chase the Dana invoice"
    base = search_agents(store, emb, query, 8, CFG)
    message = None if which == "none" else query
    assert _sig(search_agents(store, emb, query, 8, CFG, message=message)) == _sig(base)


def _noise_store(tmp_path, emb):
    s = AgentStore(tmp_path / "noise.db")
    for i in range(12):
        add(s, emb, f"ag_noise_{i:02d}", f"Quarterly budget {i}", "quarterly budget planning review meeting notes")
    add(s, emb, "ag_target", "Travel", "zanzibar itinerary")
    return s


def test_message_lifts_the_target_that_only_the_message_names(tmp_path, emb):
    s = _noise_store(tmp_path, emb)
    history = [("user", "quarterly budget planning review meeting notes quarterly budget", None)]
    query = build_query("zanzibar", history, 2)
    without = ids(search_agents(s, emb, query, 3, CFG))
    with_msg = ids(search_agents(s, emb, query, 3, CFG, message="zanzibar"))
    assert "ag_target" not in without
    assert "ag_target" in with_msg


def test_agent_id_only_in_history_is_still_referenced_with_a_message(store, emb):
    history = [("agent", "Sent the notes.", "ag_zanzibar")]
    query = build_query("lunch plans", history, 2)
    assert "ag_zanzibar" in query
    got = {c.agent_id: c for c in search_agents(store, emb, query, 3, CFG, message="lunch plans")}
    assert "ag_zanzibar" in got
    assert got["ag_zanzibar"].reasons.count("referenced") == 1


def test_reasons_are_never_duplicated_across_rankings(store, emb):
    query = "dana invoice\ndana invoice follow-up"
    for c in search_agents(store, emb, query, 8, CFG, message="dana invoice"):
        assert len(c.reasons) == len(set(c.reasons)), c
    dana = next(c for c in search_agents(store, emb, query, 8, CFG, message="dana invoice")
                if c.agent_id == "ag_dana_2")
    assert dana.reasons.count("bm25") == 1 and dana.reasons.count("embedding") == 1


@pytest.mark.parametrize("message", ["the of and", "   "])
def test_message_with_nothing_to_match_still_returns_the_history_target(store, emb, message):
    history = [("user", "plan the zanzibar trip itinerary", None)]
    query = build_query(message, history, 2)
    got = ids(search_agents(store, emb, query, 5, CFG, message=message))
    assert "ag_zanzibar" in got
