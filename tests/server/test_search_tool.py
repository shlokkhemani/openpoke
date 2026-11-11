"""Task 13-M: the guarded search_agents tool (one search per hybrid turn)."""

import asyncio
import json
from datetime import datetime, timezone

import pytest

from server.agents.interaction_agent import tools as ia_tools
from server.services.agents import indexer
from server.services.agents import store as store_module
from server.services.agents.embeddings import HashingEmbedder
from server.services.agents.store import AgentRecord, AgentStore

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
NOTE_30 = "Closest 20 of 30 agents; if none handles this task, create a new agent with `name`."


@pytest.fixture
def store30(tmp_path, monkeypatch):
    store = AgentStore(tmp_path / "agents.db")
    for i in range(30):
        agent_id = f"ag_t{i:07d}"
        store.insert_agent(AgentRecord(agent_id, f"Agent {i}", "invoice follow up", T1, None, None))
        store.set_search_text(agent_id, f"Agent {i} invoice follow up")
    monkeypatch.setattr(store_module, "_store", store)
    return store


def search(query="invoice"):
    return ia_tools.handle_tool_call("search_agents", {"query": query})


def card_count(cards):
    return cards.count("<agent id=")


def test_schema_has_query_only_and_hybrid_list_appends_it():
    fn = ia_tools.SEARCH_AGENTS_SCHEMA["function"]
    assert fn["name"] == "search_agents"
    assert set(fn["parameters"]["properties"]) == {"query"}
    assert fn["parameters"]["required"] == ["query"]
    assert fn["parameters"]["additionalProperties"] is False
    assert ia_tools.HYBRID_TOOL_SCHEMAS == [*ia_tools.TOOL_SCHEMAS, ia_tools.SEARCH_AGENTS_SCHEMA]
    assert ia_tools.get_tool_schemas() is ia_tools.TOOL_SCHEMAS  # production full list is unchanged


def test_search_returns_twenty_cards_and_note(store30):
    with ia_tools.search_turn(True):
        out = search()
    assert out.success
    assert out.payload["note"] == NOTE_30
    assert card_count(out.payload["agents"]) == 20


def test_note_counts_cards_actually_returned(tmp_path, monkeypatch):
    store = AgentStore(tmp_path / "small.db")
    for i in range(3):
        store.insert_agent(AgentRecord(f"ag_s{i:07d}", f"Agent {i}", "invoice", T1, None, None))
    monkeypatch.setattr(store_module, "_store", store)
    with ia_tools.search_turn(True):
        out = search()
    assert out.payload["note"] == (
        "Closest 3 of 3 agents; if none handles this task, create a new agent with `name`."
    )
    assert card_count(out.payload["agents"]) == 3


def test_second_search_in_a_turn_is_refused(store30):
    with ia_tools.search_turn(True):
        assert search().success
        second = search("anything else")
    assert not second.success
    assert second.payload == {"error": ia_tools.ERR_ALREADY_SEARCHED}
    assert ia_tools.ERR_ALREADY_SEARCHED == (
        "Already searched this turn. If no agent fits, create one with `name`."
    )


@pytest.mark.parametrize("query", ["", "   ", None])
def test_blank_query_errors_without_spending_the_budget(store30, query):
    with ia_tools.search_turn(True):
        bad = ia_tools.handle_tool_call("search_agents", {"query": query})
        assert not bad.success and bad.payload.get("error")
        assert bad.payload["error"] != ia_tools.ERR_ALREADY_SEARCHED
        again = search()
    assert again.success and card_count(again.payload["agents"]) == 20


def test_missing_query_argument_errors_without_spending_the_budget(store30):
    with ia_tools.search_turn(True):
        bad = ia_tools.handle_tool_call("search_agents", {})
        assert not bad.success and bad.payload.get("error")
        assert search().success


@pytest.mark.parametrize("enabled", [None, False])
def test_outside_a_hybrid_turn_it_is_an_unknown_tool(store30, enabled):
    if enabled is None:
        out = search()
    else:
        with ia_tools.search_turn(enabled):
            out = search()
    assert not out.success
    assert out.payload == {"error": "Unknown tool: search_agents"}


def test_each_turn_gets_a_fresh_budget_and_state_is_restored(store30):
    with ia_tools.search_turn(True):
        assert search().success
    with ia_tools.search_turn(True):
        assert search().success
    assert search().payload == {"error": "Unknown tool: search_agents"}


def test_concurrent_turns_each_get_their_own_budget(store30):
    results = {}

    async def turn(name):
        with ia_tools.search_turn(True):
            await asyncio.sleep(0)  # let the other turn start before this one searches
            first = search(f"invoice {name}")
            await asyncio.sleep(0)
            second = search(f"invoice {name}")
            results[name] = (first.success, second.success, second.payload)

    async def main():
        await asyncio.gather(asyncio.create_task(turn("a")), asyncio.create_task(turn("b")))

    asyncio.run(main())
    for name in ("a", "b"):
        assert results[name] == (True, False, {"error": ia_tools.ERR_ALREADY_SEARCHED})


def test_search_uses_the_ready_embedder_and_only_the_query(store30):
    class Recording(HashingEmbedder):
        def __init__(self):
            super().__init__()
            self.texts = []

        def embed(self, texts):
            self.texts.extend(texts)
            return super().embed(texts)

    emb = Recording()
    assert indexer.warm_up(emb) is not None
    emb.texts.clear()
    with ia_tools.search_turn(True):
        assert search("budget review").success
    assert emb.texts == ["budget review"]  # the model's query alone: no history, no ids


def test_search_result_is_json_serialisable(store30):
    with ia_tools.search_turn(True):
        out = search()
    json.dumps(out.payload)


# Task 14: the pure search core shared with the eval harness -------------------------------------

def test_search_agents_result_equals_the_tool_output(store30, monkeypatch):
    from server.config import get_settings
    from server.services.agents.retrieval import RetrievalConfig

    class NoTriggers:
        def list_for_agent(self, agent_id):
            return []

    monkeypatch.setattr(ia_tools, "get_trigger_service", lambda: NoTriggers())
    monkeypatch.setattr(ia_tools.indexer, "ready_embedder", lambda: None)
    with ia_tools.search_turn(True):
        via_tool = search("invoice")
    via_core = ia_tools.search_agents_result(
        "invoice", store30, None, RetrievalConfig.from_settings(get_settings()), lambda _id: [])
    assert via_core.success and via_core.payload == via_tool.payload
    assert via_core.payload["note"] == NOTE_30 and card_count(via_core.payload["agents"]) == 20


def test_search_agents_result_blank_query_is_the_blank_error_and_ignores_the_budget(store30):
    from server.services.agents.retrieval import RetrievalConfig

    out = ia_tools.search_agents_result("  ", store30, None, RetrievalConfig(), lambda _id: [])
    assert not out.success and out.payload == {"error": ia_tools.ERR_BLANK_QUERY}
    with ia_tools.search_turn(True):  # the core never touches the per-turn budget
        ia_tools.search_agents_result("invoice", store30, None, RetrievalConfig(), lambda _id: [])
        assert search().success


# Task 16f guard: the tool path has no message, so retrieval is unchanged there ---------------------

def test_search_agents_result_calls_retrieve_cards_without_a_message(store30, monkeypatch):
    from server.config import get_settings
    from server.services.agents.retrieval import RetrievalConfig

    seen = []
    real = ia_tools.retrieve_cards

    def spy(*args, **kwargs):
        seen.append(kwargs.get("message"))
        return real(*args, **kwargs)

    monkeypatch.setattr(ia_tools, "retrieve_cards", spy)
    ia_tools.search_agents_result(
        "invoice", store30, None, RetrievalConfig.from_settings(get_settings()), lambda _id: [])
    assert seen == [None]
