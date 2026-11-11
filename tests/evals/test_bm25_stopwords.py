"""Task 16e: stopwords no longer reach the BM25 query (model-free: HashingEmbedder, output under tmp_path)."""
from pathlib import Path

import pytest

import evals.textwords
import server.services.agents.stopwords as server_stopwords
from evals.caseset import V1_DIR, V2_DIR, load_frozen_cases
from evals.harness.load_world import load_into_store
from evals.retrieval_eval import case_queries
from evals.world.generate import WORLD_PATH
from evals.world.roster import load_world
from server.services.agents.embeddings import HashingEmbedder
from server.services.agents.store import AgentStore

OLD_STOPWORDS = frozenset(
    "a an and are as at be but by for from had has have he her his how i if in into is it its me my of on or our "
    "she so than that the their them then they this to up us was we were what when where which who why will with "
    "you your about re any did do does not no yes can could would should s t d m ll ve re don doesn didn isn aren wasn won".split())

CASE_ID = "multi-person-006"
N = 300


def _build(case_dir, tmp_path_factory):
    world = load_world(WORLD_PATH)
    cases = load_frozen_cases(case_dir)
    case = next(c for c in cases if c.id == CASE_ID)
    rq = next(q for q in case_queries(cases, world, case.split) if q.case_id == CASE_ID)
    # the eval's N=300 cell (evaluate()): required + context agents sorted by id, then first fillers in filler_order
    required = sorted({a.id: a for a in (*rq.required, *rq.extra_agents)}.values(), key=lambda a: a.id)
    req_ids = {a.id for a in required}
    fillers = [world.agents[i] for i in world.filler_order if i not in req_ids][: N - len(required)]
    store = AgentStore(tmp_path_factory.mktemp("bm25") / "s.db")
    load_into_store([*required, *fillers], world, store, HashingEmbedder(), {})
    ranking = [aid for aid, _ in store.fts_search(rq.query, N)]
    return rq, required, ranking, case_dir


@pytest.fixture(scope="module", params=[V1_DIR, V2_DIR], ids=["v1", "v2"])
def setup(request, tmp_path_factory):
    return _build(request.param, tmp_path_factory)


@pytest.fixture(scope="module")
def setup_v1(tmp_path_factory):
    return _build(V1_DIR, tmp_path_factory)


def test_bm25_matches_far_fewer_agents_at_n300(setup):
    _, _, ranking, case_dir = setup
    if case_dir == V1_DIR:
        assert len(ranking) <= 30
    else:
        # v2's history ("Noor replied that the slot is confirmed") carries content words that match many agents
        # (it was 300 before stopwords were dropped, 120 now), so only a strict decrease is claimed.
        assert len(ranking) < 300


def test_sam_agents_in_bm25_top10(setup_v1):
    # v1 only: on v2 the history's content words match many agents, so the top-10 claim does not hold.
    rq, required, ranking, _ = setup_v1
    assert rq.expected
    top10 = set(ranking[:10])
    assert rq.expected <= top10
    sams = {a.id for a in required if any(c.display_name in ("Sam Rivera", "Sam Okafor") for c in a.contacts)}
    assert sams and sams <= top10


def test_stopwords_shared_and_unchanged():
    assert evals.textwords.STOPWORDS is server_stopwords.STOPWORDS
    assert server_stopwords.STOPWORDS == OLD_STOPWORDS
