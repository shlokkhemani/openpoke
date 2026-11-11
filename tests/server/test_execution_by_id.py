"""Task 7: execution path keyed by agent id (runtime, agent, batch manager, IA bridge)."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from server.agents.execution_agent import agent as agent_module
from server.agents.execution_agent import batch_manager as batch_module
from server.agents.execution_agent import runtime as runtime_module
from server.agents.execution_agent.agent import ExecutionAgent
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.execution_agent.runtime import ExecutionAgentRuntime, ExecutionResult
from server.agents.interaction_agent import tools as ia_tools
from server.services.agents import store as store_module
from server.services.agents.store import AgentRecord, AgentStore
from server.services.execution import log_store as log_store_module
from server.services.execution.log_store import ExecutionAgentLogStore, _slugify

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 11, 2, 15, 30, tzinfo=timezone.utc)
T3 = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)

AGENT_ID = "ag_abcd2345"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Tmp agent store + tmp execution log store + fake settings; no network, nothing in server/data."""
    store = AgentStore(tmp_path / "agents.db")
    logs = ExecutionAgentLogStore(tmp_path / "logs")
    monkeypatch.setattr(store_module, "_store", store)
    monkeypatch.setattr(agent_module, "get_execution_agent_logs", lambda: logs)
    monkeypatch.setattr(log_store_module, "_execution_agent_logs", logs)
    monkeypatch.setattr(ia_tools, "get_execution_agent_logs", lambda: logs)
    monkeypatch.setattr(
        runtime_module,
        "get_settings",
        lambda: SimpleNamespace(openrouter_api_key="test-key", execution_agent_model="test-model"),
    )

    async def _no_network(**kwargs):
        raise AssertionError("network call attempted in a unit test")

    monkeypatch.setattr(runtime_module, "request_chat_completion", _no_network)
    return SimpleNamespace(store=store, logs=logs, tmp=tmp_path)


def add_agent(store, agent_id, name, description="", created_at=T1):
    store.insert_agent(AgentRecord(agent_id, name, description, created_at, None, None))


def result(agent_id, name, response="Sent the weekly digest."):
    return ExecutionResult(agent_id=agent_id, agent_name=name, success=True, response=response)


# --- batch payload --------------------------------------------------------------------------

def test_batch_payload_includes_id():
    assert "(agent_id=ag_1)" in ExecutionBatchManager()._format_batch_payload([result("ag_1", "Digest")])


def test_batch_payload_exact_format():
    payload = ExecutionBatchManager()._format_batch_payload(
        [result("ag_1", "Digest", "done"), ExecutionResult(agent_id="ag_2", agent_name="Payroll", success=False, response="boom")]
    )
    assert payload == "[SUCCESS] Digest (agent_id=ag_1): done\n[FAILED] Payroll (agent_id=ag_2): boom"


# --- log store ------------------------------------------------------------------------------

def test_slugify_keeps_agent_id_unchanged():
    assert _slugify(AGENT_ID) == AGENT_ID
    assert _slugify("ag_chen_budget") == "ag_chen_budget"


def test_agent_logs_keyed_by_id(env):
    add_agent(env.store, AGENT_ID, "Weekly digest", "Summarise the inbox every Monday")
    agent = ExecutionAgent(AGENT_ID, store=env.store)
    agent.record_response("hello")
    assert (env.tmp / "logs" / f"{AGENT_ID}.log").exists()
    assert "hello" in env.logs.load_transcript(AGENT_ID)


# --- agent / runtime ------------------------------------------------------------------------

def test_system_prompt_uses_store_name_and_description(env):
    add_agent(env.store, AGENT_ID, "Weekly digest", "Summarise the inbox every Monday")
    prompt = ExecutionAgent(AGENT_ID, store=env.store).build_system_prompt()
    assert "Agent Name: Weekly digest" in prompt
    assert "Purpose: Summarise the inbox every Monday" in prompt
    assert AGENT_ID not in prompt.split("Agent Name:")[1].splitlines()[0]


def test_runtime_binds_trigger_tools_to_agent_id(env):
    add_agent(env.store, AGENT_ID, "Weekly digest")
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)
    assert rt.tool_registry["createTrigger"].keywords["agent_id"] == AGENT_ID
    assert rt.tool_registry["listTriggers"].keywords["agent_id"] == AGENT_ID


def _scripted_llm(tool_name, tool_args):
    calls = {"n": 0}

    async def fake_llm(system_prompt, messages, with_tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"choices": [{"message": {"content": "", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": tool_name, "arguments": json.dumps(tool_args)}}]}}]}
        return {"choices": [{"message": {"content": "Draft created."}}]}

    return fake_llm


DRAFT_ARGS = {"recipient_email": "Alice.Chen@northwind.io", "cc": ["bob@x.io"], "subject": "s", "body": "b"}


def test_runtime_records_contacts_after_successful_tool_call(env):
    add_agent(env.store, AGENT_ID, "Northwind budget")
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)
    rt.tool_registry = {"gmail_create_draft": lambda **kw: {"successful": True, "error": None, "data": {"id": "r-1"}}}
    rt._make_llm_call = _scripted_llm("gmail_create_draft", DRAFT_ARGS)
    res = asyncio.run(rt.execute("Draft a note to Alice"))
    assert res.success and res.agent_id == AGENT_ID
    assert {(c.email, c.role) for c in env.store.contacts_for(AGENT_ID)} == {
        ("alice.chen@northwind.io", "to"), ("bob@x.io", "cc")}


def test_runtime_records_no_contacts_when_tool_raises(env):
    add_agent(env.store, AGENT_ID, "Northwind budget")
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)

    def boom(**kw):
        raise RuntimeError("GMAIL_CREATE_DRAFT invocation failed")

    rt.tool_registry = {"gmail_create_draft": boom}
    rt._make_llm_call = _scripted_llm("gmail_create_draft", DRAFT_ARGS)
    res = asyncio.run(rt.execute("Draft a note to Alice"))
    assert res.success and res.agent_id == AGENT_ID
    assert env.store.contacts_for(AGENT_ID) == []


def test_runtime_survives_contact_capture_failure(env, monkeypatch):
    add_agent(env.store, AGENT_ID, "Northwind budget")

    def broken_add(agent_id, contacts):
        raise RuntimeError("db is locked")

    monkeypatch.setattr(env.store, "add_contacts", broken_add)
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)
    rt.tool_registry = {"gmail_create_draft": lambda **kw: {"data": {"id": "r-1"}}}
    rt._make_llm_call = _scripted_llm("gmail_create_draft", DRAFT_ARGS)
    res = asyncio.run(rt.execute("Draft a note to Alice"))
    assert res.success and res.response == "Draft created." and res.agent_id == AGENT_ID


# --- batch manager --------------------------------------------------------------------------

def _quiet_manager(monkeypatch):
    manager = ExecutionBatchManager()
    dispatched = []

    async def fake_dispatch(payload):
        dispatched.append(payload)

    monkeypatch.setattr(manager, "_dispatch_to_interaction_agent", fake_dispatch)
    return manager, dispatched


def test_execute_agent_runs_runtime_by_id(env, monkeypatch):
    add_agent(env.store, AGENT_ID, "Weekly digest")
    seen = []

    class FakeRuntime:
        def __init__(self, agent_id, **kwargs):
            seen.append(agent_id)
            self.agent_id = agent_id

        async def execute(self, instructions):
            return ExecutionResult(agent_id=self.agent_id, agent_name="Weekly digest", success=True, response="ok")

    monkeypatch.setattr(batch_module, "ExecutionAgentRuntime", FakeRuntime)
    manager, dispatched = _quiet_manager(monkeypatch)
    res = asyncio.run(manager.execute_agent(AGENT_ID, "send digest"))
    assert seen == [AGENT_ID]
    assert res.success and res.agent_id == AGENT_ID
    assert dispatched == [f"[SUCCESS] Weekly digest (agent_id={AGENT_ID}): ok"]


def test_execute_agent_unknown_id_fails_cleanly(env, monkeypatch):
    manager, dispatched = _quiet_manager(monkeypatch)
    res = asyncio.run(manager.execute_agent("ag_missing1", "do something"))
    assert res.success is False
    assert res.agent_id == "ag_missing1"
    assert "ag_missing1" in (res.error or "")
    assert "unknown" in (res.error or "").lower()
    assert env.store.list_agents() == []  # no auto-create


# --- interaction agent dispatches by id (Task 9 replaced the temporary name->id bridge) ----

def _dispatch(monkeypatch, **kwargs):
    calls = []

    async def fake_execute_agent(agent_id, instructions, request_id=None):
        calls.append((agent_id, instructions))
        return SimpleNamespace(success=True)

    monkeypatch.setattr(ia_tools._EXECUTION_BATCH_MANAGER, "execute_agent", fake_execute_agent)

    async def main():
        out = ia_tools.send_message_to_agent(**kwargs)
        for _ in range(5):
            await asyncio.sleep(0)
        return out

    return asyncio.run(main()), calls


def test_ia_dispatch_by_id_ignores_duplicate_names(env, monkeypatch):
    add_agent(env.store, "ag_old00000", "Digest", created_at=T1)
    add_agent(env.store, "ag_new00000", "Digest", created_at=T2)
    out, calls = _dispatch(monkeypatch, instructions="send the digest", agent_id="ag_old00000")
    assert out.success
    assert calls == [("ag_old00000", "send the digest")]
    assert len(env.store.list_agents()) == 2
    assert "send the digest" in env.logs.load_transcript("ag_old00000")


def test_ia_dispatch_by_name_creates_agent_and_runs_it_by_id(env, monkeypatch):
    out, calls = _dispatch(monkeypatch, instructions="run payroll", name="Payroll")
    agents = env.store.list_agents()
    assert out.success
    assert [a.name for a in agents] == ["Payroll"]
    assert calls == [(agents[0].id, "run payroll")]
    assert "run payroll" in env.logs.load_transcript(agents[0].id)


def test_execute_agent_store_error_still_completes_batch(env, monkeypatch):
    def broken_get(agent_id):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(env.store, "get", broken_get)
    manager, dispatched = _quiet_manager(monkeypatch)
    res = asyncio.run(manager.execute_agent(AGENT_ID, "send digest"))
    assert res.success is False
    assert res.agent_id == AGENT_ID
    assert "database is locked" in (res.error or "")
    assert manager._batch_state is None  # batch drained
    assert len(dispatched) == 1 and dispatched[0].startswith(f"[FAILED] {AGENT_ID} (agent_id={AGENT_ID}):")
