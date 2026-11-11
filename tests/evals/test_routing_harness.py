import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pytest

from evals.clock import EVAL_NOW
from evals.grading import ToolCall
from evals.harness.fake_llm import FakeLLM
from evals.harness.render import render_legacy_roster, render_transcript
from evals.harness.routing import build_legacy_messages, run_case
from evals.schema import AgentDef, Turn, load_cases
from evals.world.roster import load_world, roster_for
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.interaction_agent import agent as ia_agent
from server.agents.interaction_agent import runtime as ia_runtime
from server.agents.interaction_agent import tools as ia_tools
from server.openrouter_client import OpenRouterError

EX = Path("evals/cases/examples")
WORLD = load_world(Path("evals/world/world.json"))
CASES = {c.id: c for c in load_cases(EX)}
IA_DIR = Path("server/agents/interaction_agent")


def by_id(case_id: str):
    return CASES[case_id]


@pytest.fixture(autouse=True)
def _no_production_side_effects(monkeypatch):
    """Any path into the real tools, the real LLM client or real agents fails the test."""

    def boom(*args, **kwargs):
        raise AssertionError("harness reached production code")

    async def aboom(*args, **kwargs):
        raise AssertionError("harness reached production code")

    monkeypatch.setattr(ia_runtime, "handle_tool_call", boom)
    monkeypatch.setattr(ia_tools, "handle_tool_call", boom)
    monkeypatch.setattr(ia_runtime, "request_chat_completion", aboom)
    monkeypatch.setattr(ExecutionBatchManager, "execute_agent", aboom)


def test_harness_records_scripted_calls():
    case = by_id("trigger-001")
    llm = FakeLLM([[ToolCall("send_message_to_user", {"message": "On it"}),
                    ToolCall("send_message_to_agent", {"agent_name": "Nightly digest", "instructions": "move to 8pm"})]])
    rec = asyncio.run(run_case(case, WORLD, "legacy", 30, llm))
    assert [c.name for c in rec.calls] == ["send_message_to_user", "send_message_to_agent"]
    assert rec.calls[1].args == {"agent_name": "Nightly digest", "instructions": "move to 8pm"}
    assert rec.round_trips == 2 and rec.error is None
    assert rec.user_messages == ["On it"]
    assert rec.final_text == FakeLLM.FINAL_TEXT
    assert (rec.prompt_tokens, rec.completion_tokens) == (
        2 * FakeLLM.PROMPT_TOKENS, 2 * FakeLLM.COMPLETION_TOKENS)
    assert (rec.case_id, rec.mode, rec.n, rec.run_idx) == ("trigger-001", "legacy", 30, 0)
    assert rec.latency_s >= 0


def test_stub_returns_real_payload_shapes():
    case = by_id("trigger-001")
    llm = FakeLLM([
        [ToolCall("send_message_to_agent", {"agent_name": "Nightly digest", "instructions": "a"}),
         ToolCall("send_message_to_agent", {"agent_name": "Brand new", "instructions": "b"}),
         ToolCall("send_message_to_agent", {"agent_name": "Brand new", "instructions": "c"})],
        [ToolCall("send_draft", {"to": "x@y.io", "subject": "S", "body": "B"}),
         ToolCall("wait", {"reason": "already sent"}),
         ToolCall("send_message_to_agent", {"agent_name": "Missing instructions"}),
         ToolCall("no_such_tool", {})],
    ])
    rec = asyncio.run(run_case(case, WORLD, "legacy", 10, llm))
    assert rec.error is None and rec.round_trips == 3
    assert len(rec.calls) == 7
    results = [json.loads(m["content"]) for m in llm.requests[-1]["messages"] if m["role"] == "tool"]
    assert results[0]["result"] == {"status": "submitted", "agent_name": "Nightly digest", "new_agent_created": False}
    assert results[1]["result"] == {"status": "submitted", "agent_name": "Brand new", "new_agent_created": True}
    assert results[2]["result"]["new_agent_created"] is False  # second call reuses the new name
    assert results[3]["result"] == {"status": "draft_recorded", "to": "x@y.io", "subject": "S"}
    assert results[4]["result"] == {"status": "waiting", "reason": "already sent"}
    assert results[5]["status"] == "error" and "Missing required arguments" in results[5]["error"]["error"]
    assert results[6]["error"] == {"error": "Unknown tool: no_such_tool"}


def _production_log(tmp_path, history):
    """A real ConversationLog on a temp file, containing ``history`` as production would log it."""
    from server.services.conversation.log import ConversationLog, _default_formatter

    path = tmp_path / "conversation.log"
    with path.open("w", encoding="utf-8") as fh:
        for i, turn in enumerate(history):
            tag = {"user": "user_message", "assistant": "poke_reply", "agent": "agent_message"}[turn.role]
            ts = (EVAL_NOW - timedelta(minutes=len(history) - i)).strftime("%Y-%m-%d %H:%M:%S")
            payload = turn.text if turn.role != "agent" else f"[SUCCESS] {turn.agent_name}: {turn.text}"
            fh.write(_default_formatter(tag, ts, payload))
    return ConversationLog(path)


def test_render_transcript_equals_production_load_transcript(tmp_path):
    history = [Turn("user", "a < b & c \"q\"\nline two"), Turn("assistant", "ok"),
               Turn("agent", "done & dusted", agent_id="ag_x", agent_name="Nightly digest")]
    assert render_transcript(history, "legacy") == _production_log(tmp_path, history).load_transcript()


def test_legacy_prompt_matches_production_rendering(monkeypatch, tmp_path):
    case = by_id("trigger-001")
    roster = roster_for(case, WORLD, 10)
    system_prompt, messages = build_legacy_messages(case, roster)

    assert system_prompt == (IA_DIR / "system_prompt_legacy.md").read_text(encoding="utf-8").strip()
    assert len(messages) == 1 and messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert content.count("<agent name=") == len(roster) == 10
    assert f"<active_agents>\n{render_legacy_roster(roster)}\n</active_agents>" in content
    assert '<agent name="Nightly digest" />' in content
    assert ('<conversation_history>\n'
            "<user_message timestamp=\"2026-11-01 11:58:00\">What's on my calendar tomorrow?</user_message>\n"
            '<poke_reply timestamp="2026-11-01 11:59:00">Two things:') in content
    assert content.endswith(f"<new_user_message>\n{case.message}\n</new_user_message>")
    assert "agent_id" not in content

    # Byte-for-byte what production builds from a real conversation log holding the same turns
    # (written with production's formatter and the harness's timestamps) and the same roster.
    log = _production_log(tmp_path, case.ia_history)
    expected = ia_agent.prepare_message_with_history(
        case.message, log.load_transcript(), message_type="user",
        roster_block=render_legacy_roster(roster))
    assert messages == expected


def test_legacy_tool_schemas_are_production_schemas():
    case = by_id("trigger-001")
    llm = FakeLLM([])
    asyncio.run(run_case(case, WORLD, "legacy", 10, llm))
    from server.agents.interaction_agent import roster_view
    assert llm.requests[0]["tools"] == roster_view.legacy_tool_schemas()
    assert llm.requests[0]["system"] == build_legacy_messages(case, roster_for(case, WORLD, 10))[0]


# sha256 of system_prompt.md at c1bc207, before the routing rules were added.
ORIGINAL_PROMPT_SHA256 = "d8257b89da9fcb47eaf980b1f9a097c8e147c45196e569e13303c04ec9a1da37"
OLD_REUSE_LINE = "Don't worry if the agent name is unrelated"


def test_system_prompt_legacy_is_the_original_prompt():
    import hashlib
    legacy = (IA_DIR / "system_prompt_legacy.md").read_bytes()
    assert hashlib.sha256(legacy).hexdigest() == ORIGINAL_PROMPT_SHA256
    assert OLD_REUSE_LINE in legacy.decode()


def test_prompt_has_new_rules_not_old_line():
    p = (IA_DIR / "system_prompt.md").read_text(encoding="utf-8")
    assert OLD_REUSE_LINE not in p
    for heading in ("One operation per agent", "People who share a first name", "Broad questions",
                    "Unclear requests"):
        assert heading in p


def test_legacy_rules_differs_from_legacy_only_in_system_prompt():
    from evals.harness.routing import SYSTEM_PROMPT_LEGACY, SYSTEM_PROMPT_RULES
    case = by_id("trigger-001")
    old, new = FakeLLM([]), FakeLLM([])
    asyncio.run(run_case(case, WORLD, "legacy", 10, old))
    asyncio.run(run_case(case, WORLD, "legacy_rules", 10, new))
    a, b = old.requests[0], new.requests[0]
    assert a["system"] == SYSTEM_PROMPT_LEGACY and b["system"] == SYSTEM_PROMPT_RULES
    assert a["system"] != b["system"]
    assert a["messages"] == b["messages"]
    from server.agents.interaction_agent import roster_view
    assert a["tools"] == b["tools"] == roster_view.legacy_tool_schemas()


def test_render_legacy_roster_matches_production_format():
    roster = [AgentDef("ag_a", 'Email "Bob" & co', "d"), AgentDef("ag_b", "Plain", "d")]
    assert render_legacy_roster(roster) == '<agent name="Email &quot;Bob&quot; &amp; co" />\n<agent name="Plain" />'
    assert render_legacy_roster([]) == "None"


def test_agent_turn_rendering_by_mode():
    t = [Turn("agent", "digest text", agent_id="ag_nightly_digest", agent_name="Nightly digest")]
    assert "agent_id=ag_nightly_digest" not in render_transcript(t, "legacy")
    assert "agent_id=ag_nightly_digest" in render_transcript(t, "hybrid")
    assert render_transcript(t, "legacy") == (
        '<agent_message timestamp="2026-11-01 11:59:00">[SUCCESS] Nightly digest: digest text</agent_message>')
    assert render_transcript(t, "full") == (
        '<agent_message timestamp="2026-11-01 11:59:00">'
        "[SUCCESS] Nightly digest (agent_id=ag_nightly_digest): digest text</agent_message>")


def test_render_transcript_tags_and_escaping():
    t = [Turn("user", "a < b & c"), Turn("assistant", "ok \"quoted\"")]
    assert render_transcript(t, "legacy") == (
        '<user_message timestamp="2026-11-01 11:58:00">a &lt; b &amp; c</user_message>\n'
        '<poke_reply timestamp="2026-11-01 11:59:00">ok "quoted"</poke_reply>')
    assert render_transcript([], "legacy") == ""
    with pytest.raises(ValueError):
        render_transcript(t, "bogus")


def test_stub_never_dispatches_real_agents():
    # The autouse fixture patches ExecutionBatchManager.execute_agent (and the real tool handler)
    # to raise; the harness run must still succeed and report submission.
    case = by_id("trigger-001")
    llm = FakeLLM([[ToolCall("send_message_to_agent", {"agent_name": "Nightly digest", "instructions": "x"})]])
    rec = asyncio.run(run_case(case, WORLD, "legacy", 30, llm))
    assert rec.error is None
    assert [c.name for c in rec.calls] == ["send_message_to_agent"]


def test_llm_error_goes_to_record_error():
    case = by_id("trigger-001")
    rec = asyncio.run(run_case(case, WORLD, "legacy", 10, FakeLLM.raising(OpenRouterError("429"))))
    assert rec.error and rec.calls == []
    assert "OpenRouterError" in rec.error and "429" in rec.error
    assert rec.round_trips == 0 and rec.prompt_tokens == 0


def test_error_after_some_calls_keeps_calls_and_tokens():
    case = by_id("trigger-001")
    inner = FakeLLM([[ToolCall("send_message_to_user", {"message": "hi"})]])
    count = {"n": 0}

    async def flaky(**kwargs):
        count["n"] += 1
        if count["n"] == 2:
            raise TimeoutError("read timed out")
        return await inner(**kwargs)

    rec = asyncio.run(run_case(case, WORLD, "legacy", 10, flaky))
    assert rec.error == "TimeoutError: read timed out"
    assert [c.name for c in rec.calls] == ["send_message_to_user"]
    assert rec.round_trips == 1 and rec.prompt_tokens == FakeLLM.PROMPT_TOKENS


def test_malformed_response_goes_to_record_error():
    async def bad(**kwargs):
        return {"choices": []}

    rec = asyncio.run(run_case(by_id("trigger-001"), WORLD, "legacy", 10, bad))
    assert rec.error and rec.error.startswith("RuntimeError")


def test_missing_usage_counts_zero_tokens():
    async def no_usage(**kwargs):
        return {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}

    rec = asyncio.run(run_case(by_id("trigger-001"), WORLD, "legacy", 10, no_usage))
    assert rec.error is None and rec.round_trips == 1
    assert (rec.prompt_tokens, rec.completion_tokens) == (0, 0)
    assert rec.final_text == "hello"


def test_fake_llm_text_and_kwargs():
    llm = FakeLLM.text("just text")
    resp = asyncio.run(llm(model="m", messages=[], system="s", api_key=None, tools=[], extra=1))
    msg = resp["choices"][0]["message"]
    assert msg["content"] == "just text" and not msg.get("tool_calls")
    assert resp["usage"]["prompt_tokens"] == FakeLLM.PROMPT_TOKENS

    scripted = FakeLLM([[ToolCall("wait", {"reason": "r"})]])
    tc = asyncio.run(scripted(model="m", messages=[]))["choices"][0]["message"]["tool_calls"][0]
    assert tc["type"] == "function" and tc["id"]
    assert tc["function"] == {"name": "wait", "arguments": '{"reason": "r"}'}


def test_default_runtime_uses_production_dependencies(monkeypatch):
    # Constructor defaults: real LLM client, real handler, real schemas, API key required.
    monkeypatch.setattr(ia_runtime, "get_settings", lambda: type("S", (), {
        "openrouter_api_key": None, "interaction_agent_model": "m", "summarization_enabled": False,
        "roster_mode": "full", "retrieval_k": 20, "retrieval_rrf_k": 60,
        "retrieval_history_turns": 2})())
    with pytest.raises(ValueError, match="OpenRouter API key"):
        ia_runtime.InteractionAgentRuntime()
    rt = ia_runtime.InteractionAgentRuntime(require_api_key=False)
    assert rt.tool_schemas is ia_tools.get_tool_schemas() is ia_tools.TOOL_SCHEMAS
    # Production defaults are the ids interface: ids schema (agent_id / name) and ids prompt.
    from server.agents.interaction_agent import roster_view
    assert ia_tools.TOOL_SCHEMAS != roster_view.legacy_tool_schemas()
    props = ia_tools.TOOL_SCHEMAS[0]["function"]["parameters"]["properties"]
    assert ia_tools.TOOL_SCHEMAS[0]["function"]["name"] == "send_message_to_agent"
    assert set(props) == {"instructions", "agent_id", "name"}
    assert ia_agent.build_system_prompt() == ia_agent.build_system_prompt("ids")
    assert ia_agent.build_system_prompt() != ia_agent.build_system_prompt("names")

    seen = {}

    async def fake_client(**kwargs):
        seen.update(kwargs)
        return {"choices": [{"message": {"content": "x"}}]}

    monkeypatch.setattr(ia_runtime, "request_chat_completion", fake_client)
    monkeypatch.setattr(ia_runtime, "handle_tool_call", lambda name, args: seen.setdefault("tool", name))
    asyncio.run(rt._make_llm_call("sys", []))
    assert seen["system"] == "sys" and seen["tools"] is ia_tools.TOOL_SCHEMAS and seen["model"] == "m"
    rt._execute_tool(ia_runtime._ToolCall("id", "wait", {"reason": "r"}))
    assert seen["tool"] == "wait"


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown roster mode"):
        asyncio.run(run_case(by_id("trigger-001"), WORLD, "recency", 10, FakeLLM([])))


@pytest.mark.parametrize("raw", [
    {"id": "call_bad", "type": "function",
     "function": {"name": "send_message_to_agent", "arguments": "{bad"}},
    {"id": "call_list", "type": "function",
     "function": {"name": "send_message_to_agent", "arguments": "[1, 2]"}},
    {"id": "call_noname", "type": "function", "function": {"arguments": "{}"}},
], ids=["invalid-json", "non-object", "nameless"])
def test_malformed_tool_call_goes_to_record_error(raw):
    llm = FakeLLM([[ToolCall("send_message_to_user", {"message": "Which one?"}), raw]])
    rec = asyncio.run(run_case(by_id("trigger-001"), WORLD, "legacy", 10, llm))
    assert rec.error and rec.error.startswith("MalformedToolCall")
    assert [c.name for c in rec.calls] == ["send_message_to_user"]  # calls kept
    assert rec.round_trips == 2


def test_well_formed_unknown_tool_is_not_malformed():
    llm = FakeLLM([[ToolCall("no_such_tool", {})]])
    rec = asyncio.run(run_case(by_id("trigger-001"), WORLD, "legacy", 10, llm))
    assert rec.error is None and [c.name for c in rec.calls] == ["no_such_tool"]
