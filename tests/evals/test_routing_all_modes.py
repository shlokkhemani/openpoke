"""Task 14: ``full`` and ``hybrid`` run through production ``build_turn_inputs`` in the routing harness.

Offline: FakeLLM and HashingEmbedder only, nothing under server/data.
"""
import asyncio
import json
import re
from pathlib import Path

import pytest

from evals.baselines import oracle
from evals.caseset import load_frozen_cases
from evals.grading import ToolCall, grade
from evals.harness import routing
from evals.harness.fake_llm import FakeLLM
from evals.harness.full_roster import render_full_roster
from evals.harness.load_world import CachedEmbedder
from evals.harness.render import render_transcript
from evals.harness.routing import run_case
from evals.retrieval_eval import expected_for
from evals.schema import load_cases
from evals.world.roster import load_world, roster_for
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.interaction_agent import agent as ia_agent
from server.agents.interaction_agent import runtime as ia_runtime
from server.agents.interaction_agent import tools as ia_tools
from server.agents.interaction_agent.roster_view import hybrid_roster_block
from server.services.agents.embeddings import HashingEmbedder

EX = Path("evals/cases/examples")
V1 = Path("evals/cases/v1")
WORLD = load_world(Path("evals/world/world.json"))
EXAMPLES = sorted(load_cases(EX), key=lambda c: c.id)
SIZES = (10, 30, 100, 300)


def embedder():
    return CachedEmbedder(HashingEmbedder())


@pytest.fixture(autouse=True)
def _no_production_side_effects(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("harness reached production code")

    async def aboom(*args, **kwargs):
        raise AssertionError("harness reached production code")

    monkeypatch.setattr(ia_runtime, "handle_tool_call", boom)
    monkeypatch.setattr(ia_tools, "handle_tool_call", boom)
    monkeypatch.setattr(ia_runtime, "request_chat_completion", aboom)
    monkeypatch.setattr(ExecutionBatchManager, "execute_agent", aboom)


def emb_kw(mode):
    """``full`` needs no embedder (none is passed); ``hybrid`` gets a hashing one."""
    return {"embedder": embedder()} if mode == "hybrid" else {}


def first_request(case, mode, n, descriptions=None):
    llm = FakeLLM([])
    rec = asyncio.run(run_case(case, WORLD, mode, n, llm, descriptions=descriptions, **emb_kw(mode)))
    assert rec.error is None
    return llm.requests[0]


# 2. full byte-identity guard -------------------------------------------------------------------

V1_CASES = sorted(load_frozen_cases(V1), key=lambda c: c.id)
SOME_DESCRIPTIONS = {aid: f"REGEN description of {aid}." for i, aid in enumerate(sorted(WORLD.agents)) if i % 3 == 0}


def test_full_goes_through_build_turn_inputs(monkeypatch):
    calls = []
    real = routing.build_turn_inputs
    monkeypatch.setattr(routing, "build_turn_inputs",
                        lambda *a, **k: calls.append(a[0]) or real(*a, **k), raising=True)
    first_request(EXAMPLES[0], "full", 10, descriptions={})
    assert calls == ["full"]


@pytest.mark.parametrize("n", SIZES)
def test_full_inputs_are_byte_identical_to_the_render_full_roster_path(n):
    for case in V1_CASES:
        req = first_request(case, "full", n, descriptions=SOME_DESCRIPTIONS)
        expected = ia_agent.prepare_message_with_history(
            case.message, render_transcript(case.ia_history, "full"), "user",
            roster_block=render_full_roster(roster_for(case, WORLD, n), SOME_DESCRIPTIONS))
        assert req["system"] == ia_agent.build_system_prompt("ids"), (case.id, n)
        assert req["messages"][0] == expected[0], (case.id, n)  # the loop appends later turns
        assert req["tools"] == ia_tools.TOOL_SCHEMAS, (case.id, n)


# 3. oracle through the harness -----------------------------------------------------------------

@pytest.mark.parametrize("mode", ["full", "hybrid"])
@pytest.mark.parametrize("n", [10, 30])
def test_oracle_calls_grade_fully_through_the_harness(mode, n):
    failures = []
    for case in EXAMPLES:
        roster = roster_for(case, WORLD, n)
        calls = oracle(case, roster).calls
        llm = FakeLLM([calls] if calls else [])
        rec = asyncio.run(run_case(case, WORLD, mode, n, llm, descriptions={}, **emb_kw(mode)))
        assert rec.error is None, (case.id, rec.error)
        g = grade(case, rec, roster, mode)
        if not g.passed:
            failures.append(case.id)
    assert failures == []


# 4. real retrieval behind hybrid search --------------------------------------------------------

def person_case():
    for c in EXAMPLES:
        if c.expect_person and expected_for(c, WORLD)[1]:
            return c
    raise AssertionError("no example case with a person")


def test_search_serves_the_agents_of_a_person_with_real_retrieval():
    case = person_case()
    _kind, target = expected_for(case, WORLD)
    llm = FakeLLM([[ToolCall("search_agents", {"query": case.expect_person})]])
    rec = asyncio.run(run_case(case, WORLD, "hybrid", 30, llm, embedder=embedder()))
    assert rec.error is None
    assert [c.name for c in rec.calls] == ["search_agents"]
    (search,) = rec.searches
    assert search["query"] == case.expect_person and search["error"] is None
    assert target <= set(search["ids"]) and len(search["ids"]) == 20
    tool_texts = [m["content"] for m in llm.requests[1]["messages"] if m.get("role") == "tool"]
    assert all(aid in tool_texts[0] for aid in target)


def test_second_search_is_refused_and_blank_query_does_not_spend_the_budget():
    case = person_case()
    llm = FakeLLM([[ToolCall("search_agents", {"query": "   "})],
                   [ToolCall("search_agents", {"query": case.expect_person})],
                   [ToolCall("search_agents", {"query": "again"})]])
    rec = asyncio.run(run_case(case, WORLD, "hybrid", 30, llm, embedder=embedder()))
    assert rec.error is None
    blank, real, second = rec.searches
    assert blank["error"] == ia_tools.ERR_BLANK_QUERY and blank["ids"] == []
    assert real["error"] is None and real["ids"]
    assert second["error"] == ia_tools.ERR_ALREADY_SEARCHED
    assert [c.name for c in rec.calls] == ["search_agents"] * 3  # recorded like any other call


def test_each_case_run_gets_a_fresh_search_budget():
    case = person_case()
    for _ in range(2):
        llm = FakeLLM([[ToolCall("search_agents", {"query": case.expect_person})]])
        rec = asyncio.run(run_case(case, WORLD, "hybrid", 30, llm, embedder=embedder()))
        assert rec.searches[0]["error"] is None


def test_hybrid_records_the_initial_twenty_ids():
    case = person_case()
    rec = asyncio.run(run_case(case, WORLD, "hybrid", 30, FakeLLM([]), embedder=embedder()))
    assert len(rec.initial_ids) == 20 and rec.searches == []
    small = asyncio.run(run_case(case, WORLD, "hybrid", 10, FakeLLM([]), embedder=embedder()))
    assert len(small.initial_ids) == 10


# 5. roster header -------------------------------------------------------------------------------

def test_hybrid_header_all_agents_shown_at_ten():
    content = first_request(EXAMPLES[0], "hybrid", 10)["messages"][0]["content"]
    assert "All 10 agents are shown." in content and content.count("<agent id=") == 10


def test_hybrid_header_offers_search_above_twenty():
    req = first_request(EXAMPLES[0], "hybrid", 30)
    content = req["messages"][0]["content"]
    header = hybrid_roster_block(30, 20, "").split("\n")[0]
    assert "These are the 20 agents most relevant to this message, of 30." in header
    assert header in content and content.count("<agent id=") == 20
    assert req["system"] == ia_agent.build_system_prompt("hybrid")
    assert req["tools"] == ia_tools.HYBRID_TOOL_SCHEMAS


# 6. determinism ---------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["full", "hybrid"])
def test_same_case_and_n_give_identical_inputs(mode):
    case = EXAMPLES[1]
    a = first_request(case, mode, 30, descriptions={})
    b = first_request(case, mode, 30, descriptions={})
    assert (a["system"], a["messages"][0], a["tools"]) == (b["system"], b["messages"][0], b["tools"])


# misc contract ----------------------------------------------------------------------------------

def test_hybrid_without_an_embedder_is_a_clear_error():
    with pytest.raises(ValueError, match="embedder"):
        asyncio.run(run_case(EXAMPLES[0], WORLD, "hybrid", 10, FakeLLM([])))


def test_full_needs_no_embedder_and_legacy_modes_are_unchanged():
    assert first_request(EXAMPLES[0], "full", 10, descriptions={})["tools"] == ia_tools.TOOL_SCHEMAS
    rec = asyncio.run(run_case(EXAMPLES[0], WORLD, "legacy", 10, FakeLLM([])))
    assert rec.error is None and rec.searches == [] and rec.initial_ids == []
