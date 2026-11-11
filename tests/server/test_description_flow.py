"""Task 8: run facts collected by the runtime, update after each run, execution prompt line."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.agents.execution_agent import agent as agent_module
from server.agents.execution_agent import batch_manager as batch_module
from server.agents.execution_agent import runtime as runtime_module
from server.agents.execution_agent.agent import SYSTEM_PROMPT_TEMPLATE
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.execution_agent.runtime import ExecutionAgentRuntime, ExecutionResult
from server.services.agents import store as store_module
from server.services.agents.store import AgentRecord, AgentStore, ContactRecord
from server.services.execution import log_store as log_store_module
from server.services.execution.log_store import ExecutionAgentLogStore

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
AGENT_ID = "ag_abcd2345"
ROOT = Path(__file__).resolve().parents[2]


def RunFacts(*args):
    from server.services.agents.descriptions import RunFacts as _RunFacts
    return _RunFacts(*args)


# --- runtime collects RunFacts --------------------------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    store = AgentStore(tmp_path / "agents.db")
    logs = ExecutionAgentLogStore(tmp_path / "logs")
    monkeypatch.setattr(store_module, "_store", store)
    monkeypatch.setattr(agent_module, "get_execution_agent_logs", lambda: logs)
    monkeypatch.setattr(log_store_module, "_execution_agent_logs", logs)
    monkeypatch.setattr(runtime_module, "get_settings",
                        lambda: SimpleNamespace(openrouter_api_key="k", execution_agent_model="m"))
    store.insert_agent(AgentRecord(AGENT_ID, "Northwind budget", "", T1, None, None))
    return SimpleNamespace(store=store)


def _scripted(calls):
    state = {"n": 0}

    async def fake_llm(system_prompt, messages, with_tools):
        n = state["n"]
        state["n"] += 1
        if n < len(calls):
            name, args = calls[n]
            return {"choices": [{"message": {"content": "", "tool_calls": [
                {"id": f"c{n}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}
        return {"choices": [{"message": {"content": "Done. Alice has not replied yet."}}]}

    return fake_llm


def test_runtime_collects_run_facts(env):
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)
    ok = lambda **kw: {"successful": True, "error": None, "data": {"id": "r"}}
    rt.tool_registry = {"gmail_create_draft": ok, "gmail_reply_to_thread": ok}
    rt._make_llm_call = _scripted([
        ("gmail_create_draft", {"recipient_email": "a@x.io", "subject": "Q3 budget", "body": "b"}),
        ("gmail_create_draft", {"recipient_email": "a@x.io", "subject": "Q3 budget", "body": "b"}),
        ("gmail_reply_to_thread", {"thread_id": "t", "recipient_email": "b@x.io", "subject": "Re: lease", "message_body": "m"}),
    ])
    res = asyncio.run(rt.execute("draft"))
    assert res.success
    assert res.facts.subjects == ["Q3 budget", "Re: lease"]
    assert {(c.email, c.role) for c in res.facts.contacts} == {("a@x.io", "to"), ("b@x.io", "to")}


def test_runtime_run_facts_capped_at_ten_subjects(env):
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)
    rt.MAX_TOOL_ITERATIONS = 20
    rt.tool_registry = {"gmail_create_draft": lambda **kw: {"data": {"id": "r"}}}
    rt._make_llm_call = _scripted([
        ("gmail_create_draft", {"recipient_email": "a@x.io", "subject": f"S{i}", "body": "b"}) for i in range(14)])
    res = asyncio.run(rt.execute("draft"))
    assert res.facts.subjects == [f"S{i}" for i in range(10)]


def test_runtime_run_facts_skip_failed_tools(env):
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)

    def boom(**kw):
        raise RuntimeError("nope")

    rt.tool_registry = {"gmail_create_draft": boom}
    rt._make_llm_call = _scripted([("gmail_create_draft", {"recipient_email": "a@x.io", "subject": "Q3", "body": "b"})])
    res = asyncio.run(rt.execute("draft"))
    assert res.facts.subjects == [] and res.facts.contacts == []


# --- batch manager: update after run, non-blocking ------------------------------------------

class SpyUpdater:
    def __init__(self, gate=None, raises=False):
        self.calls = []
        self.finished = False
        self.gate = gate
        self.raises = raises

    async def update(self, agent_id, instructions, final_response, facts=None):
        self.calls.append((agent_id, instructions, final_response, facts))
        if self.gate is not None:
            await self.gate.wait()
        if self.raises:
            raise RuntimeError("updater exploded")
        self.finished = True
        return "x"


def _manager(monkeypatch, env, updater, result):
    class FakeRuntime:
        def __init__(self, agent_id, **kw):
            self.agent_id = agent_id

        async def execute(self, instructions):
            return result

    monkeypatch.setattr(batch_module, "ExecutionAgentRuntime", FakeRuntime)
    manager = ExecutionBatchManager(description_updater=updater)
    dispatched = []

    async def fake_dispatch(payload):
        dispatched.append(payload)

    monkeypatch.setattr(manager, "_dispatch_to_interaction_agent", fake_dispatch)
    return manager


def _ok_result(facts=None):
    return ExecutionResult(agent_id=AGENT_ID, agent_name="Northwind budget", success=True,
                           response="Sent. Waiting on Alice.", facts=facts)


def test_updater_runs_after_successful_run_with_facts(env, monkeypatch):
    facts = RunFacts([ContactRecord("a@x.io", "", "to")], ["Q3"])
    spy = SpyUpdater()
    manager = _manager(monkeypatch, env, spy, _ok_result(facts))

    async def go():
        await manager.execute_agent(AGENT_ID, "email alice")
        await manager.drain_description_updates()

    asyncio.run(go())
    assert spy.calls == [(AGENT_ID, "email alice", "Sent. Waiting on Alice.", facts)]


def test_updater_not_run_on_failed_run(env, monkeypatch):
    spy = SpyUpdater()
    failed = ExecutionResult(agent_id=AGENT_ID, agent_name="n", success=False, response="boom", error="boom")
    manager = _manager(monkeypatch, env, spy, failed)

    async def go():
        await manager.execute_agent(AGENT_ID, "email alice")
        await manager.drain_description_updates()

    asyncio.run(go())
    assert spy.calls == []


def test_updater_not_run_for_unknown_agent(env, monkeypatch):
    spy = SpyUpdater()
    manager = _manager(monkeypatch, env, spy, _ok_result())

    async def go():
        res = await manager.execute_agent("ag_missing1", "x")
        await manager.drain_description_updates()
        return res

    assert asyncio.run(go()).success is False
    assert spy.calls == []


def test_result_returned_before_updater_finishes(env, monkeypatch):
    async def go():
        gate = asyncio.Event()
        spy = SpyUpdater(gate=gate)
        manager = _manager(monkeypatch, env, spy, _ok_result())
        res = await manager.execute_agent(AGENT_ID, "email alice")
        assert res.success and not spy.finished  # the IA already has its result
        gate.set()
        await manager.drain_description_updates()
        assert spy.finished

    asyncio.run(go())


def test_updater_exception_is_logged_not_raised(env, monkeypatch):
    spy = SpyUpdater(raises=True)
    manager = _manager(monkeypatch, env, spy, _ok_result())

    async def go():
        res = await manager.execute_agent(AGENT_ID, "email alice")
        await manager.drain_description_updates()  # must not raise
        return res

    assert asyncio.run(go()).success


# --- execution system prompt ----------------------------------------------------------------

def test_execution_prompt_asks_for_state_in_final_reply():
    text = (ROOT / "server" / "agents" / "execution_agent" / "system_prompt.md").read_text(encoding="utf-8")
    line = "End your final reply with where things stand: who replied and what they said, and what is still pending."
    assert text.count(line) == 1
    assert line in SYSTEM_PROMPT_TEMPLATE




# --- default updater wiring (added in GREEN) --------------------------------------------------

def test_default_updater_uses_description_model_and_agent_triggers(env, monkeypatch):
    from evals.harness.fake_llm import FakeLLM
    from server.services.triggers.models import TriggerRecord

    llm = FakeLLM.text("Chases the Northwind budget.")
    owners = []

    def list_triggers(*, agent_id):
        owners.append(agent_id)
        return [TriggerRecord(id=1, agent_id=agent_id, payload="water the ficus", status="active",
                              created_at="2026-11-01T00:00:00Z", updated_at="2026-11-01T00:00:00Z")]

    monkeypatch.setattr(batch_module, "request_chat_completion", llm)
    monkeypatch.setattr(batch_module, "get_trigger_service", lambda: SimpleNamespace(list_triggers=list_triggers))
    monkeypatch.setattr(batch_module, "get_settings",
                        lambda: SimpleNamespace(openrouter_api_key="k", description_model="haiku-test"))
    manager = _manager(monkeypatch, env, None, _ok_result())

    async def go():
        await manager.execute_agent(AGENT_ID, "email alice")
        await manager.drain_description_updates()

    asyncio.run(go())
    assert [r["model"] for r in llm.requests] == ["haiku-test"]
    assert owners == [AGENT_ID]
    assert env.store.get(AGENT_ID).description == "Chases the Northwind budget."
    assert [i for i, _ in env.store.fts_search("ficus", 5)] == [AGENT_ID]
