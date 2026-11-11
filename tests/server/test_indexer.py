"""Task 13-I (branch-review I3): one indexer gives every refresh path real embeddings."""

import asyncio
import importlib
import sys
import threading
import time
import types
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from server.agents.execution_agent import agent as agent_module
from server.agents.execution_agent import batch_manager as batch_module
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.interaction_agent import tools as ia_tools
from server.config import get_settings
from server.services import triggers as triggers_pkg
from server.services.agents import embeddings as embeddings_module
from server.services.agents import indexer
from server.services.agents import store as store_module
from server.services.agents.descriptions import DescriptionUpdater
from server.services.agents.embeddings import FastEmbedder, HashingEmbedder
from server.services.agents.store import AgentRecord, AgentStore
from server.services.execution import log_store as log_store_module
from server.services.execution.log_store import ExecutionAgentLogStore
from server.services.triggers.service import TriggerService
from server.services.triggers.store import TriggerStore

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
AGENT_ID = "ag_abcd2345"
app_module = importlib.import_module("server.app")  # `server.app` the attribute is the FastAPI instance
DIM = 256
REAL_MAKE_EMBEDDER = indexer._make_embedder  # captured before the autouse fixture stubs it


def has_embedding(store, agent_id, dim=DIM):
    ids, _ = store.embeddings(dim)
    return agent_id in ids


def blob(store, agent_id):
    row = store._query("SELECT embedding FROM agents WHERE id = ?", (agent_id,))[0]
    return row["embedding"]


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = AgentStore(tmp_path / "agents.db")
    monkeypatch.setattr(store_module, "_store", s)
    s.insert_agent(AgentRecord(AGENT_ID, "Northwind budget", "", T1, None, None))
    return s


class Boom:
    def embed(self, texts):
        raise RuntimeError("model load failed")


# --- test isolation fixture (tests/conftest.py) ---------------------------------------------

def test_isolation_fixture_resets_state_and_blocks_real_embedder():
    assert indexer._embedder is None and indexer._dim is None
    assert indexer.ready_embedder() is None
    with pytest.raises(Exception):
        indexer._make_embedder()


# --- warm-up -------------------------------------------------------------------------------

def test_before_warm_up_indexing_writes_search_text_only(store):
    indexer.index_agent(AGENT_ID)
    assert [i for i, _ in store.fts_search("Northwind", 5)] == [AGENT_ID]
    assert blob(store, AGENT_ID) is None
    assert indexer.ready_embedder() is None


def test_warm_up_publishes_embedder_and_dim():
    emb = HashingEmbedder()
    assert indexer.warm_up(emb) == DIM
    assert indexer.ready_embedder() is emb
    assert indexer._dim == DIM


def test_warm_up_without_argument_builds_the_configured_embedder(monkeypatch):
    emb = HashingEmbedder(64)
    monkeypatch.setattr(indexer, "_make_embedder", lambda: emb)
    assert indexer.warm_up() == 64
    assert indexer.ready_embedder() is emb


def test_warm_up_failure_leaves_not_ready_and_never_raises():
    assert indexer.warm_up(Boom()) is None
    assert indexer.ready_embedder() is None
    assert indexer._dim is None


def test_warm_up_build_failure_never_raises():
    # the conftest fixture makes _make_embedder raise
    assert indexer.warm_up() is None
    assert indexer.ready_embedder() is None


def test_empty_embedding_model_means_bm25_only_and_builds_nothing(monkeypatch):
    built = []
    monkeypatch.setattr(indexer, "_make_embedder", lambda: built.append(1) or HashingEmbedder())
    monkeypatch.setattr(get_settings(), "embedding_model", "")
    assert indexer.warm_up() is None
    assert built == []
    assert indexer.ready_embedder() is None


def test_make_embedder_uses_the_configured_model(monkeypatch):
    made = []

    class Spy:
        def __init__(self, model):
            made.append(model)

    monkeypatch.setattr(get_settings(), "embedding_model", "x/y")
    monkeypatch.setattr(indexer, "FastEmbedder", Spy)
    monkeypatch.setattr(indexer, "_make_embedder", REAL_MAKE_EMBEDDER)
    assert isinstance(indexer._make_embedder(), Spy)
    assert made == ["x/y"]


# --- index_agent / backfill -----------------------------------------------------------------

def test_index_agent_after_warm_up_writes_embedding(store):
    indexer.warm_up(HashingEmbedder())
    indexer.index_agent(AGENT_ID)
    assert has_embedding(store, AGENT_ID)


def test_index_agent_uses_given_triggers_instead_of_the_service(store, monkeypatch):
    calls = []
    monkeypatch.setattr(indexer, "refresh_search_index", lambda *a, **k: calls.append(a))
    marker = ["t"]
    indexer.index_agent(AGENT_ID, marker)
    assert calls and calls[0][1] == AGENT_ID and calls[0][2] == marker


def test_index_agent_fetches_triggers_from_the_service_when_none(store, monkeypatch):
    calls = []
    monkeypatch.setattr(indexer, "refresh_search_index", lambda *a, **k: calls.append(a))
    svc = triggers_pkg.get_trigger_service()
    monkeypatch.setattr(svc, "list_for_agent", lambda agent_id: ["from-service"], raising=False)
    indexer.index_agent(AGENT_ID)
    assert calls[0][2] == ["from-service"]


def _three_agents(store):
    for aid in ("ag_null", "ag_short", "ag_good"):
        store.insert_agent(AgentRecord(aid, f"Name {aid}", "", T1, None, None))
        store.set_search_text(aid, f"name {aid}")
    store.set_embedding("ag_short", np.ones(8, dtype=np.float32))
    sentinel = np.zeros(DIM, dtype=np.float32)
    sentinel[0] = 1.0
    store.set_embedding("ag_good", sentinel)
    return sentinel


def test_ids_needing_embedding_covers_null_and_wrong_size(store):
    _three_agents(store)
    assert sorted(store.ids_needing_embedding(DIM)) == sorted([AGENT_ID, "ag_null", "ag_short"])
    assert store.ids_needing_embedding(8) != []
    assert "ag_short" not in store.ids_needing_embedding(8)


def test_backfill_is_a_noop_when_not_warmed_up(store):
    _three_agents(store)
    assert indexer.backfill_embeddings(store) == 0
    assert blob(store, "ag_null") is None


def test_backfill_embeds_only_rows_needing_it(store):
    sentinel = _three_agents(store)
    before = blob(store, "ag_good")
    indexer.warm_up(HashingEmbedder())
    assert indexer.backfill_embeddings(store) == 3
    assert store.ids_needing_embedding(DIM) == []
    assert blob(store, "ag_good") == before  # untouched
    assert np.frombuffer(blob(store, "ag_good"), dtype=np.float32).tolist() == sentinel.tolist()
    assert indexer.backfill_embeddings(store) == 0


def test_backfill_defaults_to_the_agent_store_singleton(store):
    indexer.warm_up(HashingEmbedder())
    assert indexer.backfill_embeddings() == 1
    assert has_embedding(store, AGENT_ID)


# --- warm_and_backfill ----------------------------------------------------------------------

def test_warm_and_backfill_warms_then_backfills(store, monkeypatch):
    monkeypatch.setattr(indexer, "_make_embedder", lambda: HashingEmbedder())
    indexer.warm_and_backfill()
    assert indexer.ready_embedder() is not None
    assert has_embedding(store, AGENT_ID)


def test_warm_and_backfill_never_raises_when_the_model_cannot_load(store):
    indexer.warm_and_backfill()  # fixture's _make_embedder raises
    assert indexer.ready_embedder() is None
    assert blob(store, AGENT_ID) is None


def test_warm_and_backfill_never_raises_when_steps_raise(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(indexer, "warm_up", boom)
    indexer.warm_and_backfill()
    monkeypatch.setattr(indexer, "warm_up", lambda *a, **k: 1)
    monkeypatch.setattr(indexer, "backfill_embeddings", boom)
    indexer.warm_and_backfill()


# --- every refresh path embeds ---------------------------------------------------------------

@pytest.fixture
def logs(tmp_path, monkeypatch):
    lg = ExecutionAgentLogStore(tmp_path / "logs")
    monkeypatch.setattr(agent_module, "get_execution_agent_logs", lambda: lg)
    monkeypatch.setattr(log_store_module, "_execution_agent_logs", lg)
    monkeypatch.setattr(ia_tools, "get_execution_agent_logs", lambda: lg)
    return lg


def test_agent_created_through_the_ia_create_path_has_an_embedding_after_warm_up(store, logs, monkeypatch):
    async def fake_execute_agent(agent_id, instructions, request_id=None):
        return SimpleNamespace(success=True)

    monkeypatch.setattr(ia_tools._EXECUTION_BATCH_MANAGER, "execute_agent", fake_execute_agent)
    indexer.warm_up(HashingEmbedder())

    async def main():
        out = ia_tools.send_message_to_agent("email Alice about the offsite", name="Email Alice re offsite")
        for _ in range(5):
            await asyncio.sleep(0)
        return out

    out = asyncio.run(main())
    assert out.success
    assert has_embedding(store, out.payload["agent_id"])


def test_create_path_before_warm_up_is_text_only(store, logs, monkeypatch):
    async def fake_execute_agent(agent_id, instructions, request_id=None):
        return SimpleNamespace(success=True)

    monkeypatch.setattr(ia_tools._EXECUTION_BATCH_MANAGER, "execute_agent", fake_execute_agent)

    async def main():
        out = ia_tools.send_message_to_agent("email Alice about the offsite", name="Email Alice re offsite")
        await asyncio.sleep(0)
        return out

    out = asyncio.run(main())
    new_id = out.payload["agent_id"]
    assert [i for i, _ in store.fts_search("offsite", 5)] == [new_id]
    assert blob(store, new_id) is None


def test_batch_manager_run_path_goes_through_index_agent(store, monkeypatch):
    seen = []
    monkeypatch.setattr(indexer, "index_agent", lambda agent_id, triggers=None: seen.append(agent_id))
    ExecutionBatchManager(description_updater=object())._refresh_search_index(AGENT_ID)
    assert seen == [AGENT_ID]


def test_batch_manager_run_path_embeds_after_warm_up(store):
    indexer.warm_up(HashingEmbedder())
    ExecutionBatchManager(description_updater=object())._refresh_search_index(AGENT_ID)
    assert has_embedding(store, AGENT_ID)


def test_batch_manager_run_path_never_raises_when_indexing_fails(store, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(indexer, "index_agent", boom)
    ExecutionBatchManager(description_updater=object())._refresh_search_index(AGENT_ID)


def test_trigger_path_goes_through_index_agent(store, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(indexer, "index_agent", lambda agent_id, triggers=None: seen.append((agent_id, triggers)))
    TriggerService(TriggerStore(tmp_path / "t.db"))._refresh_search_index(AGENT_ID)
    assert [a for a, _ in seen] == [AGENT_ID]


def test_trigger_path_embeds_after_warm_up(store, tmp_path):
    indexer.warm_up(HashingEmbedder())
    TriggerService(TriggerStore(tmp_path / "t.db"))._refresh_search_index(AGENT_ID)
    assert has_embedding(store, AGENT_ID)


def test_description_path_via_batch_manager_goes_through_index_agent(store, monkeypatch):
    seen = []
    monkeypatch.setattr(indexer, "index_agent", lambda agent_id, triggers=None: seen.append(agent_id))
    updater = ExecutionBatchManager()._get_description_updater()

    async def llm(**kwargs):
        return {"choices": [{"message": {"content": "Handles the Northwind budget thread."}}]}

    updater.llm = llm
    asyncio.run(updater.update(AGENT_ID, "email alice", "done"))
    assert seen == [AGENT_ID]
    assert store.get(AGENT_ID).description == "Handles the Northwind budget thread."


def test_description_path_via_batch_manager_embeds_after_warm_up(store):
    indexer.warm_up(HashingEmbedder())
    updater = ExecutionBatchManager()._get_description_updater()

    async def llm(**kwargs):
        return {"choices": [{"message": {"content": "Handles the Northwind budget thread."}}]}

    updater.llm = llm
    asyncio.run(updater.update(AGENT_ID, "email alice", "done"))
    assert has_embedding(store, AGENT_ID)


def test_description_updater_index_callable_replaces_the_refresh(store):
    seen = []

    async def llm(**kwargs):
        return {"choices": [{"message": {"content": "A description."}}]}

    updater = DescriptionUpdater(store, llm, "m", index=lambda agent_id, *a: seen.append(agent_id))
    asyncio.run(updater.update(AGENT_ID, "email alice", "done"))
    assert seen == [AGENT_ID]
    assert [i for i, _ in store.fts_search("description", 5)] == []  # refresh_search_index not used


def test_description_updater_standalone_keeps_its_current_behaviour(store):
    async def llm(**kwargs):
        return {"choices": [{"message": {"content": "A description."}}]}

    emb = HashingEmbedder()
    updater = DescriptionUpdater(store, llm, "m", embedder=emb)
    asyncio.run(updater.update(AGENT_ID, "email alice", "done"))
    assert has_embedding(store, AGENT_ID)
    assert [i for i, _ in store.fts_search("description", 5)] == [AGENT_ID]


# --- FastEmbedder lock -------------------------------------------------------------------------

def test_fast_embedder_loads_its_model_once_under_threads(monkeypatch):
    inits = []

    class FakeTextEmbedding:
        def __init__(self, model_name):
            inits.append(model_name)
            time.sleep(0.05)

        def embed(self, texts):
            return iter([np.ones(4, dtype=np.float32) for _ in texts])

    fake = types.ModuleType("fastembed")
    fake.TextEmbedding = FakeTextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", fake)

    fe = FastEmbedder("some/model")
    barrier = threading.Barrier(8)
    errors = []

    def work():
        try:
            barrier.wait()
            fe.embed(["a"])
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert inits == ["some/model"]


# --- lazy singletons ---------------------------------------------------------------------------

def _hammer(fn):
    barrier = threading.Barrier(8)
    out = []

    def work():
        barrier.wait()
        out.append(fn())

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return out


def test_get_agent_store_is_built_once_under_concurrency(monkeypatch):
    built = []

    class SlowStore:
        def __init__(self, path):
            built.append(path)
            time.sleep(0.05)

    monkeypatch.setattr(store_module, "AgentStore", SlowStore)
    got = _hammer(store_module.get_agent_store)
    assert len(built) == 1
    assert all(g is got[0] for g in got)


def test_get_trigger_service_is_built_once_under_concurrency(monkeypatch):
    built = []

    class SlowTriggerStore:
        def __init__(self, path):
            built.append(path)
            time.sleep(0.05)

    monkeypatch.setattr(triggers_pkg, "TriggerStore", SlowTriggerStore)
    got = _hammer(triggers_pkg.get_trigger_service)
    assert len(built) == 1
    assert all(g is got[0] for g in got)


# --- startup -----------------------------------------------------------------------------------

def test_startup_schedules_warm_up_and_backfill_on_a_worker_thread(monkeypatch):
    class FakeService:
        async def start(self):
            pass

    monkeypatch.setattr(app_module, "get_trigger_scheduler", lambda: FakeService())
    monkeypatch.setattr(app_module, "get_important_email_watcher", lambda: FakeService())
    started, release = threading.Event(), threading.Event()
    ran_on = []

    def fake_warm_and_backfill():
        ran_on.append(threading.get_ident())
        started.set()
        release.wait(5)

    monkeypatch.setattr(indexer, "warm_and_backfill", fake_warm_and_backfill)
    monkeypatch.setattr(app_module, "_warmup_task", None, raising=False)

    async def main():
        await app_module._start_trigger_scheduler()  # returns while warm-up is still blocked
        task = app_module._warmup_task
        assert task is not None and not task.done()
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()
        assert ran_on[0] != threading.get_ident()
        release.set()
        await task

    asyncio.run(main())
