"""Task 9: the IA dispatches by agent id (reuse) or name (create); production runtime on ids."""

import asyncio
import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from evals.grading import ToolCall
from evals.harness.fake_llm import FakeLLM
from server.agents.interaction_agent import agent as ia_agent
from server.agents.interaction_agent import runtime as ia_runtime
from server.agents.interaction_agent import tools as ia_tools
from server.services.agents import store as store_module
from server.services.agents.store import AgentRecord, AgentStore
from server.services.execution.log_store import ExecutionAgentLogStore

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
DIGEST = "ag_digest01"
NEW_ID = re.compile(r"^ag_[a-z2-7]{8}$")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Tmp agent store and execution logs; dispatches recorded, never run."""
    store = AgentStore(tmp_path / "agents.db")
    store.insert_agent(AgentRecord(DIGEST, "Digest", "Weekly inbox digest", T1, None, None))
    logs = ExecutionAgentLogStore(tmp_path / "logs")
    dispatched = []

    async def fake_execute_agent(agent_id, instructions, request_id=None):
        dispatched.append((agent_id, instructions))
        return SimpleNamespace(success=True)

    monkeypatch.setattr(store_module, "_store", store)
    monkeypatch.setattr(ia_tools, "get_execution_agent_logs", lambda: logs)
    monkeypatch.setattr(ia_tools._EXECUTION_BATCH_MANAGER, "execute_agent", fake_execute_agent)
    return SimpleNamespace(store=store, logs=logs, dispatched=dispatched)


def call(fn, *args, **kwargs):
    """Run a tool inside an event loop and let its dispatch task run."""

    async def main():
        out = fn(*args, **kwargs)
        for _ in range(5):
            await asyncio.sleep(0)
        return out

    return asyncio.run(main())


def snapshot(store):
    return [(a.id, a.name, a.last_user_activity_at, a.last_run_at) for a in store.list_agents()]


# --- send_message_to_agent ------------------------------------------------------------------

def test_reuse_by_id(env):
    out = call(ia_tools.send_message_to_agent, "send the digest", agent_id=DIGEST)
    assert out.success
    assert out.payload == {"status": "submitted", "agent_id": DIGEST, "new_agent_created": False}
    assert env.dispatched == [(DIGEST, "send the digest")]
    assert [a.id for a in env.store.list_agents()] == [DIGEST]
    assert "send the digest" in env.logs.load_transcript(DIGEST)


def test_create_by_name_returns_id(env):
    out = call(ia_tools.send_message_to_agent, "email Alice about the offsite", name="Email Alice re offsite")
    assert out.success
    new_id = out.payload["agent_id"]
    assert out.payload == {"status": "submitted", "agent_id": new_id, "new_agent_created": True}
    assert NEW_ID.match(new_id)
    assert env.store.get(new_id).name == "Email Alice re offsite"
    assert env.dispatched == [(new_id, "email Alice about the offsite")]


def test_create_by_name_twice_makes_two_agents(env):
    a = call(ia_tools.send_message_to_agent, "x", name="Digest")
    b = call(ia_tools.send_message_to_agent, "y", name="Digest")
    assert a.payload["agent_id"] != b.payload["agent_id"] != DIGEST
    assert len(env.store.list_agents()) == 3


@pytest.mark.parametrize("kwargs", [{"agent_id": DIGEST, "name": "y"}, {}])
def test_both_or_neither_rejected(env, kwargs):  # Review Focus 3
    before = snapshot(env.store)
    out = call(ia_tools.send_message_to_agent, "x", **kwargs)
    assert not out.success
    assert isinstance(out.payload, dict) and out.payload.get("error")
    assert snapshot(env.store) == before  # nothing created, no use recorded
    assert env.dispatched == []
    assert env.logs.load_transcript(DIGEST) == ""


def test_unknown_id_rejected(env):  # Review Focus 3
    before = snapshot(env.store)
    out = call(ia_tools.send_message_to_agent, "x", agent_id="ag_nope")
    assert not out.success
    assert "unknown agent_id" in out.payload["error"]
    assert snapshot(env.store) == before
    assert env.dispatched == []
    assert env.logs.load_transcript("ag_nope") == ""


def test_user_turn_records_user_use(env):
    call(ia_tools.send_message_to_agent, "send it", agent_id=DIGEST)
    agent = env.store.get(DIGEST)
    assert agent.last_user_activity_at is not None and agent.last_run_at is not None


def test_handle_tool_call_dispatches_by_id(env):
    out = call(ia_tools.handle_tool_call, "send_message_to_agent",
               '{"agent_id": "ag_digest01", "instructions": "send it"}')
    assert out.success and env.dispatched == [(DIGEST, "send it")]


def test_handle_tool_call_rejects_agent_name_clearly(env):
    before = snapshot(env.store)
    out = call(ia_tools.handle_tool_call, "send_message_to_agent",
               {"agent_name": "Digest", "instructions": "send it"})
    assert not out.success
    assert "agent_name" in out.payload["error"]
    assert "agent_id" in out.payload["error"] and "name" in out.payload["error"]
    assert snapshot(env.store) == before and env.dispatched == []


# --- schemas --------------------------------------------------------------------------------

def test_production_schema_is_ids():
    from server.agents.interaction_agent.roster_view import legacy_tool_schemas

    schemas = ia_tools.get_tool_schemas()
    assert schemas is ia_tools.TOOL_SCHEMAS
    fn = schemas[0]["function"]
    assert fn["name"] == "send_message_to_agent"
    assert set(fn["parameters"]["properties"]) == {"instructions", "agent_id", "name"}
    assert fn["parameters"]["required"] == ["instructions"]
    assert fn["parameters"]["additionalProperties"] is False
    assert schemas[1:] == legacy_tool_schemas()[1:]  # other tools unchanged


# --- runtime: ids prompt, ids roster block, turn type ---------------------------------------

class FakeConversationLog:
    """Records writes like the real log and replays them through ``iter_entries``."""

    def __init__(self):
        self.entries = []
        self.raw = []

    def seed(self, *entries):
        self.raw.extend(entries)

    def iter_entries(self):
        return iter(list(self.raw))

    def load_transcript(self):
        return ""

    def record_user_message(self, text):
        self.entries.append(("user", text))
        self.raw.append(("user_message", "ts", text))

    def record_agent_message(self, text):
        self.entries.append(("agent", text))
        self.raw.append(("agent_message", "ts", text))

    def record_reply(self, text):
        self.entries.append(("reply", text))
        self.raw.append(("poke_reply", "ts", text))


@pytest.fixture
def runtime_env(env, monkeypatch):
    settings = SimpleNamespace(openrouter_api_key=None, interaction_agent_model="m",
                               summarization_enabled=False, roster_mode="full",
                               retrieval_k=20, retrieval_rrf_k=60, retrieval_history_turns=2)
    log = FakeConversationLog()
    monkeypatch.setattr(ia_runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(ia_runtime, "get_conversation_log", lambda: log)
    monkeypatch.setattr(ia_runtime, "get_working_memory_log", lambda: None)
    env.settings, env.log = settings, log
    return env


def _runtime(llm):
    return ia_runtime.InteractionAgentRuntime(llm=llm, require_api_key=False)


def test_full_turn_uses_ids_prompt_schema_and_cards(runtime_env):
    llm = FakeLLM([[ToolCall("send_message_to_agent", {"agent_id": DIGEST, "instructions": "send it"})]])
    result = asyncio.run(_runtime(llm).execute("send the digest"))
    assert result.success, result.error
    req = llm.requests[0]
    assert req["system"] == ia_agent.build_system_prompt("ids")
    assert req["tools"] == ia_tools.TOOL_SCHEMAS
    content = req["messages"][0]["content"]
    assert (
        "<active_agents>\n"
        '<agent id="ag_digest01" name="Digest" last_active="2026-11-01">\n'
        "description: Weekly inbox digest\n"
        "</agent>\n</active_agents>"
    ) in content
    assert result.execution_agents_used == 1
    assert runtime_env.dispatched == [(DIGEST, "send it")]
    assert runtime_env.store.get(DIGEST).last_user_activity_at is not None


def test_hybrid_turn_sends_hybrid_prompt_header_and_search_schema(runtime_env):
    runtime_env.settings.roster_mode = "hybrid"
    llm = FakeLLM.text("ok")
    result = asyncio.run(_runtime(llm).execute("send the digest"))
    assert result.success, result.error
    req = llm.requests[0]
    assert req["system"] == ia_agent.build_system_prompt("hybrid")
    assert req["tools"] == ia_tools.HYBRID_TOOL_SCHEMAS
    assert [t["function"]["name"] for t in req["tools"]][-1] == "search_agents"
    content = req["messages"][0]["content"]
    assert '<active_agents>\nAll 1 agents are shown.\n<agent id="ag_digest01"' in content


def test_hybrid_turn_second_search_gets_the_error_and_budget_is_released(runtime_env):
    runtime_env.settings.roster_mode = "hybrid"
    llm = FakeLLM([[ToolCall("search_agents", {"query": "digest"})],
                   [ToolCall("search_agents", {"query": "digest again"})]])
    result = asyncio.run(_runtime(llm).execute("find the digest agent"))
    assert result.success, result.error
    tool_messages = [m for m in llm.requests[-1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 2
    first, second = (json.loads(m["content"]) for m in tool_messages)
    assert first["status"] == "success" and "ag_digest01" in first["result"]["agents"]
    assert second["status"] == "error" and second["error"] == {"error": ia_tools.ERR_ALREADY_SEARCHED}
    # the budget does not leak out of the turn
    assert ia_tools.handle_tool_call("search_agents", {"query": "x"}).payload == {
        "error": "Unknown tool: search_agents"}


def test_full_turn_has_no_search_tool(runtime_env):
    llm = FakeLLM([[ToolCall("search_agents", {"query": "digest"})]])
    asyncio.run(_runtime(llm).execute("hi"))
    tool_message = [m for m in llm.requests[-1]["messages"] if m["role"] == "tool"][0]
    assert json.loads(tool_message["content"])["error"] == {"error": "Unknown tool: search_agents"}


def test_constructor_schema_override_wins_over_the_mode(runtime_env):
    runtime_env.settings.roster_mode = "hybrid"
    custom = [{"type": "function", "function": {"name": "wait", "parameters": {"type": "object"}}}]
    llm = FakeLLM.text("ok")
    rt = ia_runtime.InteractionAgentRuntime(llm=llm, tool_schemas=custom, require_api_key=False)
    asyncio.run(rt.execute("hi"))
    assert llm.requests[0]["tools"] is custom


@pytest.mark.parametrize("entry, message", [("execute", "new user msg"), ("handle_agent_message", "new agent msg")])
def test_turn_inputs_see_history_without_the_current_message(runtime_env, monkeypatch, entry, message):
    from server.agents.interaction_agent import turn_inputs
    from server.services.agents import indexer
    from server.services.agents.embeddings import HashingEmbedder
    from server.services.agents.retrieval import RetrievalConfig

    indexer.warm_up(HashingEmbedder())
    runtime_env.log.seed(
        ("user_message", "t1", "earlier question"),
        ("agent_message", "t2", "[SUCCESS] Digest (agent_id=ag_digest01): sent"),
    )
    calls = []
    real = turn_inputs.build_turn_inputs

    def spy(mode, store, embedder, msg, history, *, triggers_for, cfg):
        calls.append((mode, store, embedder, msg, list(history), cfg))
        return real(mode, store, embedder, msg, history, triggers_for=triggers_for, cfg=cfg)

    monkeypatch.setattr(ia_runtime, "build_turn_inputs", spy)
    result = asyncio.run(getattr(_runtime(FakeLLM.text("ok")), entry)(message))
    assert result.success, result.error
    (mode, store, embedder, msg, history, cfg), = calls
    assert mode == "full" and msg == message
    assert store is runtime_env.store
    assert embedder is indexer.ready_embedder() and embedder is not None
    assert cfg == RetrievalConfig.from_settings(runtime_env.settings)
    assert history == [("user", "earlier question", None), ("agent", "sent", "ag_digest01")]


def test_agent_turn_records_agent_use(runtime_env):
    llm = FakeLLM([[ToolCall("send_message_to_agent", {"agent_id": DIGEST, "instructions": "follow up"})]])
    result = asyncio.run(_runtime(llm).handle_agent_message("[SUCCESS] Digest (agent_id=ag_digest01): sent"))
    assert result.success, result.error
    assert runtime_env.dispatched == [(DIGEST, "follow up")]
    agent = runtime_env.store.get(DIGEST)
    assert agent.last_run_at is not None
    assert agent.last_user_activity_at is None  # an agent turn is not user activity


def test_execution_agents_used_counts_created_agents(runtime_env):
    llm = FakeLLM([[ToolCall("send_message_to_agent", {"name": "Email Alice", "instructions": "a"}),
                    ToolCall("send_message_to_agent", {"agent_id": DIGEST, "instructions": "b"})]])
    result = asyncio.run(_runtime(llm).execute("two things"))
    assert result.execution_agents_used == 2


# --- added in GREEN: turn-type scoping, blank arguments --------------------------------------

def test_turn_type_is_reset_after_each_turn(runtime_env):
    seen = []

    def handler(name, args):
        seen.append(ia_tools.current_turn_type())
        return ia_tools.ToolResult(success=True, payload={"status": "waiting"})

    async def main():
        script = [[ToolCall("wait", {"reason": "r"})]]
        rt = ia_runtime.InteractionAgentRuntime(llm=FakeLLM(script), tool_handler=handler,
                                                require_api_key=False)
        await rt.handle_agent_message("report")
        after_agent = ia_tools.current_turn_type()
        rt = ia_runtime.InteractionAgentRuntime(llm=FakeLLM(script), tool_handler=handler,
                                                require_api_key=False)
        await rt.execute("hi")
        return after_agent

    assert asyncio.run(main()) == "user"
    assert seen == ["agent", "user"]


def test_turn_type_reset_when_loop_raises(runtime_env):
    async def main():
        rt = _runtime(FakeLLM.raising(RuntimeError("boom")))
        result = await rt.handle_agent_message("report")
        return result, ia_tools.current_turn_type()

    result, after = asyncio.run(main())
    assert not result.success and after == "user"


def test_concurrent_turns_do_not_share_turn_type(runtime_env):
    store = runtime_env.store
    store.insert_agent(AgentRecord("ag_other001", "Other", "", T1, None, None))

    class SlowLLM(FakeLLM):
        async def __call__(self, **kwargs):
            for _ in range(3):
                await asyncio.sleep(0)  # interleave the two turns
            return await super().__call__(**kwargs)

    async def main():
        user_rt = _runtime(SlowLLM([[ToolCall("send_message_to_agent", {"agent_id": DIGEST, "instructions": "u"})]]))
        agent_rt = _runtime(SlowLLM([[ToolCall("send_message_to_agent", {"agent_id": "ag_other001", "instructions": "a"})]]))
        await asyncio.gather(agent_rt.handle_agent_message("report"), user_rt.execute("hi"))
        for _ in range(5):
            await asyncio.sleep(0)

    asyncio.run(main())
    assert store.get(DIGEST).last_user_activity_at is not None
    assert store.get("ag_other001").last_user_activity_at is None
    assert store.get("ag_other001").last_run_at is not None


def test_blank_arguments_count_as_absent(env):
    out = call(ia_tools.send_message_to_agent, "x", agent_id="  ", name="New one")
    assert out.success and out.payload["new_agent_created"] is True
    before = snapshot(env.store)
    out = call(ia_tools.send_message_to_agent, "x", agent_id="", name=" ")
    assert not out.success and snapshot(env.store) == before
