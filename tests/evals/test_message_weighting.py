"""Task 16f: retrieval also ranks on the message (model-free: HashingEmbedder, output under tmp_path)."""
import pytest

from evals.caseset import V2_DIR, load_frozen_cases
from evals.harness.load_world import load_into_store
from evals.retrieval_eval import case_queries
from evals.world.generate import WORLD_PATH
from evals.world.roster import load_world
from server.services.agents.embeddings import HashingEmbedder
from server.services.agents.retrieval import RetrievalConfig, search_agents
from server.services.agents.store import AgentStore

CASE_ID = "multi-person-006"
N = 300


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    # same N=300 cell as evaluate() and tests/evals/test_bm25_stopwords.py::_build
    world = load_world(WORLD_PATH)
    cases = load_frozen_cases(V2_DIR)
    case = next(c for c in cases if c.id == CASE_ID)
    rq = next(q for q in case_queries(cases, world, case.split) if q.case_id == CASE_ID)
    required = sorted({a.id: a for a in (*rq.required, *rq.extra_agents)}.values(), key=lambda a: a.id)
    req_ids = {a.id for a in required}
    fillers = [world.agents[i] for i in world.filler_order if i not in req_ids][: N - len(required)]
    store = AgentStore(tmp_path_factory.mktemp("msgw") / "s.db")
    load_into_store([*required, *fillers], world, store, HashingEmbedder(), {})
    return rq, store


def _ranks(rq, found):
    order = [c.agent_id for c in found]
    return {a: order.index(a) + 1 if a in order else None for a in rq.expected}


def test_expected_sams_are_in_the_top_20_when_the_message_is_ranked(setup):
    rq, store = setup
    assert rq.expected
    found = search_agents(store, HashingEmbedder(), rq.query, N, RetrievalConfig(), message=rq.message)
    ranks = _ranks(rq, found)
    assert all(r is not None and r <= 20 for r in ranks.values()), ranks


def test_without_the_message_at_least_one_expected_agent_is_outside_the_top_20(setup):
    rq, store = setup
    found = search_agents(store, HashingEmbedder(), rq.query, N, RetrievalConfig())
    ranks = _ranks(rq, found)
    assert any(r is None or r > 20 for r in ranks.values()), ranks
