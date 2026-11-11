"""Phase 2 fix 4 (review I4): subjects from task_email_search results reach the run facts."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from evals.grading import ToolCall
from evals.harness.fake_llm import FakeLLM
from server.agents.execution_agent import agent as agent_module
from server.agents.execution_agent import runtime as runtime_module
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.execution_agent.runtime import ExecutionAgentRuntime
from server.agents.execution_agent.tasks.search_email.schemas import GmailSearchEmail
from server.services.agents import store as store_module
from server.services.agents.contacts import extract_subjects
from server.services.agents.descriptions import DescriptionUpdater
from server.services.agents.store import AgentRecord, AgentStore
from server.services.execution import log_store as log_store_module
from server.services.execution.log_store import ExecutionAgentLogStore

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
AGENT_ID = "ag_abcd2345"


def search_result(*subjects):
    """What ``task_email_search`` returns on success: a list of ``GmailSearchEmail.model_dump`` dicts."""
    return [
        GmailSearchEmail(
            id=f"m-{i}", thread_id=f"t-{i}", query="northwind", subject=subject,
            sender="Alice Chen <alice.chen@northwind.io>", recipient="Me <me@example.com>",
            timestamp=T1 + timedelta(hours=i), label_ids=["INBOX"], clean_text=f"body {i}",
            has_attachments=False, attachment_count=0, attachment_filenames=[],
        ).model_dump(exclude_none=True)
        for i, subject in enumerate(subjects)
    ]


def test_search_result_subjects_in_order():
    result = search_result("Q3 budget", "Lease renewal", "Offsite dates")
    assert extract_subjects("task_email_search", {"search_query": "northwind"}, result) == [
        "Q3 budget", "Lease renewal", "Offsite dates"]


def test_search_error_result_gives_nothing():
    assert extract_subjects("task_email_search", {"search_query": "x"}, {"error": "Gmail not connected"}) == []
    assert extract_subjects("task_email_search", {"search_query": "x"}, []) == []


# --- runtime: deduped and capped through RunFacts ----------------------------------------------

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
        return {"choices": [{"message": {"content": "Found them."}}]}

    return fake_llm


def test_runtime_search_subjects_deduped_in_order(env):
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)
    rt.tool_registry = {"task_email_search": lambda **kw: search_result("Q3 budget", "Lease renewal", "Q3 budget")}
    rt._make_llm_call = _scripted([("task_email_search", {"search_query": "northwind"})])
    res = asyncio.run(rt.execute("find the budget thread"))
    assert res.success
    assert res.facts.subjects == ["Q3 budget", "Lease renewal"]


def test_runtime_search_subjects_capped_at_ten(env):
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)
    rt.tool_registry = {"task_email_search": lambda **kw: search_result(*[f"S{i}" for i in range(14)])}
    rt._make_llm_call = _scripted([("task_email_search", {"search_query": "northwind"})])
    res = asyncio.run(rt.execute("find everything"))
    assert res.facts.subjects == [f"S{i}" for i in range(10)]


def test_runtime_search_error_adds_no_subjects(env):
    rt = ExecutionAgentRuntime(AGENT_ID, store=env.store)
    rt.tool_registry = {"task_email_search": lambda **kw: {"error": "Gmail not connected"}}
    rt._make_llm_call = _scripted([("task_email_search", {"search_query": "northwind"})])
    res = asyncio.run(rt.execute("find"))
    assert res.facts.subjects == []


# --- end to end: search subjects reach the description updater's prompt ------------------------

def test_search_only_run_subjects_reach_updater_prompt(env, monkeypatch):
    registry = {"task_email_search": lambda **kw: search_result("Q3 budget", "Lease renewal")}
    monkeypatch.setattr(runtime_module, "get_tool_registry", lambda *a, **kw: registry)
    monkeypatch.setattr(runtime_module, "request_chat_completion",
                        FakeLLM([[ToolCall("task_email_search", {"search_query": "northwind"})]],
                                final_text="Found the budget thread."))
    describe_llm = FakeLLM.text("Tracks the Northwind Q3 budget thread.")
    manager = ExecutionBatchManager(description_updater=DescriptionUpdater(env.store, describe_llm, "haiku-test"))

    async def fake_dispatch(payload):
        pass

    monkeypatch.setattr(manager, "_dispatch_to_interaction_agent", fake_dispatch)

    async def go():
        res = await manager.execute_agent(AGENT_ID, "find the budget thread")
        await manager.drain_description_updates()
        return res

    assert asyncio.run(go()).success
    prompt = describe_llm.requests[0]["messages"][0]["content"]
    assert "Email subjects: Q3 budget; Lease renewal" in prompt
