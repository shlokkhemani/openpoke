"""Phase 2 fix 1 (review I1): every agent is in the search index, whatever its runs did."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from server.agents.execution_agent import agent as agent_module
from server.agents.execution_agent import batch_manager as batch_module
from server.agents.execution_agent import runtime as runtime_module
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.execution_agent.runtime import ExecutionResult
from server.agents.interaction_agent import tools as ia_tools
from server.services.agents import store as store_module
from server.services.agents.store import AgentRecord, AgentStore, ContactRecord
from server.services.execution import log_store as log_store_module
from server.services.execution.log_store import ExecutionAgentLogStore
from server.services.triggers.service import TriggerService
from server.services.triggers.store import TriggerStore

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
AGENT_ID = "ag_abcd2345"


def ids(store, query):
    return [i for i, _ in store.fts_search(query, 5)]


class RaisingSetSearchText:
    """Stand-in for ``AgentStore.set_search_text`` that counts calls and always raises."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("fts down")


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = AgentStore(tmp_path / "agents.db")
    logs = ExecutionAgentLogStore(tmp_path / "logs")
    monkeypatch.setattr(store_module, "_store", store)
    monkeypatch.setattr(agent_module, "get_execution_agent_logs", lambda: logs)
    monkeypatch.setattr(log_store_module, "_execution_agent_logs", logs)
    monkeypatch.setattr(ia_tools, "get_execution_agent_logs", lambda: logs)
    monkeypatch.setattr(runtime_module, "get_settings",
                        lambda: SimpleNamespace(openrouter_api_key="k", execution_agent_model="m"))
    store.insert_agent(AgentRecord(AGENT_ID, "Northwind budget", "", T1, None, None))
    return SimpleNamespace(store=store, logs=logs)


class SpyUpdater:
    """Records calls; never touches the index (so any refresh seen comes from the batch manager)."""

    def __init__(self):
        self.calls = []

    async def update(self, agent_id, instructions, final_response, facts=None):
        self.calls.append(agent_id)
        return "x"


def _manager(monkeypatch, execute, timeout_seconds=90):
    class FakeRuntime:
        def __init__(self, agent_id, **kw):
            self.agent_id = agent_id

        async def execute(self, instructions):
            return await execute(self.agent_id, instructions)

    monkeypatch.setattr(batch_module, "ExecutionAgentRuntime", FakeRuntime)
    manager = ExecutionBatchManager(timeout_seconds=timeout_seconds, description_updater=SpyUpdater())
    manager.dispatched = []

    async def fake_dispatch(payload):
        manager.dispatched.append(payload)

    monkeypatch.setattr(manager, "_dispatch_to_interaction_agent", fake_dispatch)
    return manager


def _run(manager, agent_id=AGENT_ID, instructions="email alice"):
    async def go():
        res = await manager.execute_agent(agent_id, instructions)
        await manager.drain_description_updates()
        return res

    return asyncio.run(go())


def _failed(response="Failed to complete task: boom"):
    return ExecutionResult(agent_id=AGENT_ID, agent_name="Northwind budget", success=False,
                           response=response, error="boom")


# --- IA create path -------------------------------------------------------------------------

@pytest.fixture
def ia_env(env, monkeypatch):
    dispatched = []

    async def fake_execute_agent(agent_id, instructions, request_id=None):
        dispatched.append((agent_id, instructions))
        return SimpleNamespace(success=True)

    monkeypatch.setattr(ia_tools._EXECUTION_BATCH_MANAGER, "execute_agent", fake_execute_agent)
    env.dispatched = dispatched
    return env


def _call(fn, *args, **kwargs):
    async def main():
        out = fn(*args, **kwargs)
        for _ in range(5):
            await asyncio.sleep(0)
        return out

    return asyncio.run(main())


def test_agent_created_by_name_is_searchable(ia_env):
    out = _call(ia_tools.send_message_to_agent, "email Alice about the offsite", name="Email Alice re offsite")
    assert out.success
    new_id = out.payload["agent_id"]
    assert ids(ia_env.store, "offsite") == [new_id]


def test_create_index_failure_never_fails_dispatch(ia_env, monkeypatch):
    spy = RaisingSetSearchText()
    monkeypatch.setattr(ia_env.store, "set_search_text", spy)
    out = _call(ia_tools.send_message_to_agent, "email Alice about the offsite", name="Email Alice re offsite")
    assert spy.calls >= 1  # the create path tried to index the new agent
    assert out.success and out.payload["new_agent_created"] is True
    assert ia_env.dispatched == [(out.payload["agent_id"], "email Alice about the offsite")]


# --- after every run ------------------------------------------------------------------------

def test_failed_run_agent_is_searchable_with_its_new_contact(env, monkeypatch):
    async def execute(agent_id, instructions):
        # A draft was created (contact recorded), then the loop died.
        env.store.add_contacts(agent_id, [ContactRecord("dana.wu@acme.io", "", "to")])
        return _failed()

    res = _run(_manager(monkeypatch, execute))
    assert res.success is False
    assert ids(env.store, "Northwind") == [AGENT_ID]
    assert ids(env.store, "dana.wu@acme.io") == [AGENT_ID]


def test_timed_out_run_agent_is_searchable(env, monkeypatch):
    async def execute(agent_id, instructions):
        await asyncio.sleep(5)

    res = _run(_manager(monkeypatch, execute, timeout_seconds=0.05))
    assert res.success is False and res.error == "Timeout"
    assert ids(env.store, "Northwind") == [AGENT_ID]


def test_unexpected_error_run_agent_is_searchable(env, monkeypatch):
    async def execute(agent_id, instructions):
        raise RuntimeError("kaboom")

    res = _run(_manager(monkeypatch, execute))
    assert res.success is False and res.error == "kaboom"
    assert ids(env.store, "Northwind") == [AGENT_ID]


def test_run_index_failure_never_changes_result_or_dispatch(env, monkeypatch):
    spy = RaisingSetSearchText()
    monkeypatch.setattr(env.store, "set_search_text", spy)
    failed = _failed("Failed to complete task: boom")

    async def execute(agent_id, instructions):
        return failed

    manager = _manager(monkeypatch, execute)
    res = _run(manager)
    assert spy.calls >= 1  # the end-of-run refresh was attempted
    assert res is failed
    assert manager.dispatched == [
        f"[FAILED] Northwind budget (agent_id={AGENT_ID}): Failed to complete task: boom"
    ]


# --- real runtime: contacts and names from a failed run reach the search text ------------------

def test_failed_real_run_contact_and_header_name_reach_search_text(env, monkeypatch):
    search_result = [{
        "id": "m-1", "thread_id": "t-1", "query": "from:alice", "subject": "Q3 budget",
        "sender": "Alice Chen <Alice.Chen@northwind.io>", "recipient": "Me <me@example.com>",
        "timestamp": T1, "label_ids": ["INBOX"], "clean_text": "numbers attached",
        "has_attachments": False, "attachment_count": 0, "attachment_filenames": [],
    }]
    registry = {
        "gmail_create_draft": lambda **kw: {"successful": True, "error": None, "data": {"id": "r-1"}},
        "task_email_search": lambda **kw: search_result,
    }
    monkeypatch.setattr(runtime_module, "get_tool_registry", lambda *a, **kw: registry)
    calls = [
        ("gmail_create_draft", {"recipient_email": "alice.chen@northwind.io", "subject": "Q3", "body": "b"}),
        ("task_email_search", {"search_query": "from:alice"}),
    ]
    state = {"n": 0}

    async def fake_llm(**kwargs):
        n = state["n"]
        state["n"] += 1
        if n < len(calls):
            name, args = calls[n]
            return {"choices": [{"message": {"content": "", "tool_calls": [
                {"id": f"c{n}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}
        raise RuntimeError("provider down")

    monkeypatch.setattr(runtime_module, "request_chat_completion", fake_llm)
    manager = ExecutionBatchManager(description_updater=SpyUpdater())

    async def fake_dispatch(payload):
        pass

    monkeypatch.setattr(manager, "_dispatch_to_interaction_agent", fake_dispatch)
    res = _run(manager)
    assert res.success is False
    assert ids(env.store, "Chen") == [AGENT_ID]
    assert ids(env.store, "alice.chen@northwind.io") == [AGENT_ID]


# --- triggers: completion and clear_next_fire -------------------------------------------------

@pytest.fixture
def agents(tmp_path, monkeypatch):
    store = AgentStore(tmp_path / "agents2.db")
    monkeypatch.setattr(store_module, "_store", store)
    return store


def _exhaustible(tmp_path, agents):
    a = agents.create_agent("Rent", "")
    svc = TriggerService(TriggerStore(tmp_path / "triggers.db"))
    t = svc.create_trigger(
        agent_id=a.id, payload="pay rent reminder", recurrence_rule="FREQ=DAILY;COUNT=1",
        start_time="2030-01-01T21:00:00", timezone_name="America/Vancouver")
    return a, svc, t


AFTER_LAST = datetime(2030, 1, 2, 6, 0, tzinfo=timezone.utc)  # after the single 9pm occurrence


def test_exhausted_recurrence_drops_trigger_from_search_text(tmp_path, agents):
    a, svc, t = _exhaustible(tmp_path, agents)
    assert ids(agents, "rent reminder") == [a.id] and ids(agents, "daily") == [a.id]
    done = svc.schedule_next_occurrence(t, fired_at=AFTER_LAST)
    assert done.status == "completed"
    assert ids(agents, "reminder") == []
    assert ids(agents, "daily") == []
    assert ids(agents, "Rent") == [a.id]  # the agent itself stays indexed


def test_clear_next_fire_rebuilds_search_text(tmp_path, agents):
    a, svc, t = _exhaustible(tmp_path, agents)
    agents.set_search_text(a.id, "stale placeholder")
    svc.clear_next_fire(t.id, agent_id=a.id)
    assert ids(agents, "placeholder") == []
    assert ids(agents, "rent reminder") == [a.id]


def test_trigger_completion_index_failure_never_fails_op(tmp_path, agents, monkeypatch):
    a, svc, t = _exhaustible(tmp_path, agents)
    spy = RaisingSetSearchText()
    monkeypatch.setattr(agents, "set_search_text", spy)
    done = svc.schedule_next_occurrence(t, fired_at=AFTER_LAST)
    assert spy.calls >= 1
    assert done.status == "completed" and done.next_trigger is None


def test_clear_next_fire_index_failure_never_fails_op(tmp_path, agents, monkeypatch):
    a, svc, t = _exhaustible(tmp_path, agents)
    spy = RaisingSetSearchText()
    monkeypatch.setattr(agents, "set_search_text", spy)
    cleared = svc.clear_next_fire(t.id, agent_id=a.id)
    assert spy.calls >= 1
    assert cleared.id == t.id and cleared.next_trigger is None
