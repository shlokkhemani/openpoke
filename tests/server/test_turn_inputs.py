"""Task 13-M: hybrid prompt, cards and roster blocks, history_from_log, build_turn_inputs."""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from server.agents.interaction_agent import agent as ia_agent
from server.services.agents.retrieval import RetrievalConfig
from server.services.agents.store import AgentRecord, AgentStore

IA_DIR = Path("server/agents/interaction_agent")
T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
CFG = RetrievalConfig()  # k=20, rrf_k=60, history_turns=2

# sha256 of build_system_prompt("ids") at the start of Task 13-M: "full" must not change.
IDS_PROMPT_SHA256 = "51607697cf61f214ca54c14a5f85398c12e86bcf809c1f3bf7c37e159534aa3c"


def no_triggers(agent_id):
    return []


def make_store(tmp_path, n, text=lambda i: f"agent number {i}"):
    store = AgentStore(tmp_path / "agents.db")
    for i in range(n):
        agent_id = f"ag_t{i:07d}"
        store.insert_agent(AgentRecord(agent_id, f"Agent {i}", text(i), T1, None, None))
        store.set_search_text(agent_id, f"Agent {i} {text(i)}")
    return store


def agent_ids_in(block):
    return re.findall(r'<agent id="(ag_[a-z0-9_]+)"', block)


class BoomEmbedder:
    def embed(self, texts):
        raise RuntimeError("embedding service down")


# --- 2. prompts -----------------------------------------------------------------------------

def test_ids_prompt_is_unchanged():
    assert hashlib.sha256(ia_agent.build_system_prompt("ids").encode("utf-8")).hexdigest() == IDS_PROMPT_SHA256


def test_hybrid_prompt_is_ids_plus_addendum():
    addendum = (IA_DIR / "prompt_tools_hybrid.md").read_text(encoding="utf-8").strip()
    ids_block = (IA_DIR / "prompt_tools_ids.md").read_text(encoding="utf-8").strip()
    ids, hybrid = ia_agent.build_system_prompt("ids"), ia_agent.build_system_prompt("hybrid")
    assert "search_agents" in addendum and "once" in addendum and "are shown" in addendum
    assert hybrid.count(addendum) == 1
    assert re.search(re.escape(ids_block) + r"\s+" + re.escape(addendum), hybrid)
    assert hybrid.replace(addendum, "").split() == ids.split()  # nothing else differs


# --- 3. history_from_log --------------------------------------------------------------------

def test_history_from_log_maps_tags_and_drops_wait():
    from server.services.agents.retrieval import history_from_log

    entries = [
        ("user_message", "t1", "hi"),
        ("poke_reply", "t2", "hello"),
        ("wait", "t3", "nothing to add"),
        ("agent_message", "t4", "[SUCCESS] Email Alice (agent_id=ag_a0000001): Sent it."),
        ("agent_message", "t5", "plain text, no id"),
        ("agent_message", "t6", "[FAILED] Digest (agent_id=ag_b0000001): boom"),
    ]
    assert history_from_log(entries) == [
        ("user", "hi", None),
        ("assistant", "hello", None),
        ("agent", "Sent it.", "ag_a0000001"),
        ("agent", "plain text, no id", None),
        ("agent", "boom", "ag_b0000001"),
    ]


def test_history_from_log_multi_entry_agent_message_keeps_payload_and_first_id():
    from server.services.agents.retrieval import history_from_log

    payload = "[SUCCESS] A (agent_id=ag_a0000001): one\n[FAILED] B (agent_id=ag_b0000001): two"
    assert history_from_log([("agent_message", "t", payload)]) == [("agent", payload, "ag_a0000001")]


def test_history_from_log_accepts_an_iterator():
    from server.services.agents.retrieval import history_from_log

    assert history_from_log(iter([("user_message", "t", "x")])) == [("user", "x", None)]


# --- 4. cards and blocks --------------------------------------------------------------------

def test_render_cards_skips_missing_ids_and_keeps_order(tmp_path):
    from server.agents.interaction_agent.roster_view import render_candidate, render_cards

    store = make_store(tmp_path, 3)
    out = render_cards(store, ["ag_t0000002", "ag_missing1", "ag_t0000000"], no_triggers)
    assert out == "\n".join(
        render_candidate(store.get(i), store.contacts_for(i), []) for i in ("ag_t0000002", "ag_t0000000")
    )


def test_render_cards_empty_is_none(tmp_path):
    from server.agents.interaction_agent.roster_view import render_cards

    store = make_store(tmp_path, 2)
    assert render_cards(store, [], no_triggers) == "None"
    assert render_cards(store, ["ag_missing1"], no_triggers) == "None"


def test_hybrid_block_no_agents_is_none():
    from server.agents.interaction_agent.roster_view import hybrid_roster_block

    assert hybrid_roster_block(0, 20, "None") == "None"


@pytest.mark.parametrize("n", [5, 20])
def test_hybrid_block_all_shown_when_n_at_most_k(n):
    from server.agents.interaction_agent.roster_view import hybrid_roster_block

    assert hybrid_roster_block(n, 20, "CARDS") == f"All {n} agents are shown.\nCARDS"


def test_hybrid_block_partial_header_names_k_and_n():
    from server.agents.interaction_agent.roster_view import hybrid_roster_block

    assert hybrid_roster_block(300, 20, "CARDS") == (
        "These are the 20 agents most relevant to this message, of 300. "
        "If none fits, call `search_agents` before creating a new agent.\nCARDS"
    )
    assert "the 7 agents most relevant to this message, of 9." in hybrid_roster_block(9, 7, "C")


def test_id_only_roster_renderer_is_gone():
    from server.agents.interaction_agent import roster_view

    assert not hasattr(roster_view, "render_id_" + "roster")


def test_retrieve_cards_returns_total_ids_and_cards(tmp_path):
    from server.agents.interaction_agent.roster_view import render_cards, retrieve_cards

    store = make_store(tmp_path, 30, lambda i: "invoice" if i < 3 else "other")
    n, ids, cards = retrieve_cards(store, None, "invoice", CFG, no_triggers)
    assert n == 30 and len(ids) == 20
    assert set(ids) >= {"ag_t0000000", "ag_t0000001", "ag_t0000002"}
    assert cards == render_cards(store, ids, no_triggers)


def test_retrieve_cards_falls_back_to_bm25_when_embedding_raises(tmp_path):
    from server.agents.interaction_agent.roster_view import retrieve_cards

    store = make_store(tmp_path, 30, lambda i: "invoice" if i < 3 else "other")
    n, ids, _ = retrieve_cards(store, BoomEmbedder(), "invoice", CFG, no_triggers)
    assert n == 30 and set(ids) >= {"ag_t0000000", "ag_t0000001", "ag_t0000002"}


# --- 1 and 5. build_turn_inputs -------------------------------------------------------------

@pytest.mark.parametrize("mode", ["legacy", "legacy_rules", "recency", "adaptive"])
def test_build_turn_inputs_rejects_non_production_modes(tmp_path, mode):
    from server.agents.interaction_agent.turn_inputs import build_turn_inputs

    store = make_store(tmp_path, 2)
    with pytest.raises(ValueError):
        build_turn_inputs(mode, store, None, "hi", [], triggers_for=no_triggers, cfg=CFG)


def test_full_mode_shows_every_agent_as_a_card(tmp_path):
    from server.agents.interaction_agent.roster_view import render_cards
    from server.agents.interaction_agent.tools import TOOL_SCHEMAS
    from server.agents.interaction_agent.turn_inputs import build_turn_inputs

    store = make_store(tmp_path, 25)
    out = build_turn_inputs("full", store, None, "hi", [], triggers_for=no_triggers, cfg=CFG)
    assert out.system_prompt == ia_agent.build_system_prompt("ids")
    assert len(agent_ids_in(out.roster_block)) == 25
    assert out.roster_block == render_cards(store, [a.id for a in store.list_agents()], no_triggers)
    assert out.tool_schemas == TOOL_SCHEMAS
    assert out.search_tool is False


def test_hybrid_mode_shows_k_cards_header_and_search_schema(tmp_path):
    from server.agents.interaction_agent.tools import HYBRID_TOOL_SCHEMAS
    from server.agents.interaction_agent.turn_inputs import build_turn_inputs

    store = make_store(tmp_path, 30, lambda i: "invoice")
    out = build_turn_inputs("hybrid", store, None, "invoice", [], triggers_for=no_triggers, cfg=CFG)
    assert out.system_prompt == ia_agent.build_system_prompt("hybrid")
    assert out.roster_block.startswith(
        "These are the 20 agents most relevant to this message, of 30. "
        "If none fits, call `search_agents` before creating a new agent.\n<agent id="
    )
    assert len(agent_ids_in(out.roster_block)) == 20
    assert out.search_tool is True
    assert out.tool_schemas == HYBRID_TOOL_SCHEMAS
    search = out.tool_schemas[-1]["function"]
    assert search["name"] == "search_agents"
    assert set(search["parameters"]["properties"]) == {"query"}
    assert search["parameters"]["required"] == ["query"]


def test_hybrid_small_roster_says_all_shown(tmp_path):
    from server.agents.interaction_agent.turn_inputs import build_turn_inputs

    store = make_store(tmp_path, 4)
    out = build_turn_inputs("hybrid", store, None, "hi", [], triggers_for=no_triggers, cfg=CFG)
    assert out.roster_block.startswith("All 4 agents are shown.\n")
    assert out.search_tool is True  # stable schema regardless of N


def test_hybrid_keeps_agent_referenced_in_last_exchange(tmp_path):
    from server.agents.interaction_agent.turn_inputs import build_turn_inputs

    store = make_store(tmp_path, 30, lambda i: "zebra" if i == 29 else "invoice")
    history = [("agent", "Sent the report.", "ag_t0000029")]
    out = build_turn_inputs("hybrid", store, None, "invoice", history, triggers_for=no_triggers, cfg=CFG)
    assert "ag_t0000029" in agent_ids_in(out.roster_block)


def test_history_beyond_the_last_exchange_is_not_used(tmp_path):
    from server.agents.interaction_agent.turn_inputs import build_turn_inputs

    store = make_store(tmp_path, 30, lambda i: "zebra" if i == 29 else "invoice")
    history = [("agent", "old", "ag_t0000029"), ("user", "u", None), ("assistant", "a", None)]
    out = build_turn_inputs("hybrid", store, None, "invoice", history, triggers_for=no_triggers, cfg=CFG)
    assert "ag_t0000029" not in agent_ids_in(out.roster_block)


@pytest.mark.parametrize("mode", ["full", "hybrid"])
def test_empty_store_gives_none_block(tmp_path, mode):
    from server.agents.interaction_agent.turn_inputs import build_turn_inputs

    store = AgentStore(tmp_path / "empty.db")
    out = build_turn_inputs(mode, store, None, "hi", [], triggers_for=no_triggers, cfg=CFG)
    assert out.roster_block == "None"


def test_hybrid_falls_back_to_bm25_when_embedder_raises(tmp_path):
    from server.agents.interaction_agent.turn_inputs import build_turn_inputs

    store = make_store(tmp_path, 30, lambda i: "invoice" if i < 3 else "other")
    out = build_turn_inputs("hybrid", store, BoomEmbedder(), "invoice", [], triggers_for=no_triggers, cfg=CFG)
    assert len(agent_ids_in(out.roster_block)) == 20
    assert {"ag_t0000000", "ag_t0000001", "ag_t0000002"} <= set(agent_ids_in(out.roster_block))


# --- Task 16f: the message reaches retrieval -------------------------------------------------

def test_hybrid_turn_passes_the_message_to_retrieve_cards_and_search_agents(tmp_path, monkeypatch):
    from server.agents.interaction_agent import roster_view, turn_inputs

    store = make_store(tmp_path, 30, lambda i: "invoice" if i < 3 else "other")
    seen = {"retrieve": [], "search": []}
    real_retrieve, real_search = turn_inputs.retrieve_cards, roster_view.search_agents

    def spy_retrieve(*a, **kw):
        seen["retrieve"].append(kw.get("message"))
        return real_retrieve(*a, **kw)

    def spy_search(*a, **kw):
        seen["search"].append(kw.get("message"))
        return real_search(*a, **kw)

    monkeypatch.setattr(turn_inputs, "retrieve_cards", spy_retrieve)
    monkeypatch.setattr(roster_view, "search_agents", spy_search)
    history = [("user", "earlier talk", None), ("assistant", "ok", None)]
    turn_inputs.build_turn_inputs("hybrid", store, None, "invoice", history, triggers_for=no_triggers, cfg=CFG)
    assert seen["retrieve"] == ["invoice"] and seen["search"] == ["invoice"]


def test_bm25_only_retry_also_receives_the_message(tmp_path, monkeypatch):
    from server.agents.interaction_agent import roster_view
    from server.agents.interaction_agent.turn_inputs import build_turn_inputs

    store = make_store(tmp_path, 30, lambda i: "invoice" if i < 3 else "other")
    calls = []
    real_search = roster_view.search_agents

    def spy_search(store_, embedder, *a, **kw):
        calls.append((embedder, kw.get("message")))
        return real_search(store_, embedder, *a, **kw)

    monkeypatch.setattr(roster_view, "search_agents", spy_search)
    history = [("user", "earlier talk", None), ("assistant", "ok", None)]
    build_turn_inputs("hybrid", store, BoomEmbedder(), "invoice", history, triggers_for=no_triggers, cfg=CFG)
    assert len(calls) == 2
    assert [m for _, m in calls] == ["invoice", "invoice"]
    assert calls[0][0] is not None and calls[1][0] is None
