"""Task 13a (F1): ``full`` roster mode in the eval harness. Offline: FakeLLM and tmp paths only."""
import asyncio
import hashlib
import json
import re
from pathlib import Path

import pytest

from evals import regen_descriptions as rd
from evals import routing_run as rr
from evals import run as run_mod
from evals.clock import EVAL_NOW, days_ago
from evals.grading import Dispatch, RunRecord, ToolCall, classify, grade
from evals.harness import routing
from evals.harness.fake_llm import FakeLLM
from evals.harness.render import render_transcript
from evals.harness.routing import LegacyToolStub, run_case
from evals.pricing import HAIKU
from evals.schema import AgentDef, Case, Contact, Outcome, Trigger, load_cases
from evals.world.roster import load_world, roster_for
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.interaction_agent import agent as ia_agent
from server.agents.interaction_agent import roster_view
from server.agents.interaction_agent import runtime as ia_runtime
from server.agents.interaction_agent import tools as ia_tools
from server.services.agents import store as store_module
from server.services.agents.store import AgentRecord, AgentStore

EX = Path("evals/cases/examples")
CASES_DIR = Path("evals/cases/v1")
WORLD = load_world(Path("evals/world/world.json"))
CASES = {c.id: c for c in load_cases(EX)}
THREE = ["clear-person-005", "amb-person-006", "newtask-005"]
NEW_ID_RE = r"^ag_new\d{5}$"
RUN_HINT = "python -m evals.run regen-descriptions"

DANA = Contact("dana@maplerentals.com", "Dana Whitfield", "to")
STANDUP = AgentDef(
    "ag_standup", "Standup reminder", "Reminds the user every day at 8am to post the standup.",
    contacts=(DANA,),
    triggers=(Trigger("daily at 8am", "Remind the user to post the standup", "active"),
              Trigger("weekly on Friday at 5pm", "Remind the user to file the timesheet", "paused")),
    last_user_activity_days_ago=3,
)
SEARCH = AgentDef("ag_search", "Find flight receipt", "Searched the inbox for the Air Canada receipt.",
                  last_user_activity_days_ago=40)


# New code under test, imported per test so each test fails on its own (strict TDD, RED half).
def render_full_roster(*args, **kwargs):
    from evals.harness.full_roster import render_full_roster as f
    return f(*args, **kwargs)


def description_coverage(*args, **kwargs):
    from evals.harness.full_roster import description_coverage as f
    return f(*args, **kwargs)


def created_agent_id(k):
    from evals.grading import created_agent_id as f
    return f(k)


def IdToolStub(roster):  # noqa: N802 - stands in for the class
    from evals.harness.routing import IdToolStub as cls
    return cls(roster)


@pytest.fixture(autouse=True)
def _no_production_side_effects(monkeypatch):
    """Any path into the real tool handler, the real LLM client or real agents fails the test."""

    def boom(*args, **kwargs):
        raise AssertionError("harness reached production code")

    async def aboom(*args, **kwargs):
        raise AssertionError("harness reached production code")

    monkeypatch.setattr(ia_runtime, "handle_tool_call", boom)
    monkeypatch.setattr(ia_tools, "handle_tool_call", boom)
    monkeypatch.setattr(ia_runtime, "request_chat_completion", aboom)
    monkeypatch.setattr(ExecutionBatchManager, "execute_agent", aboom)
    monkeypatch.setattr(rr, "default_llm", aboom)


def record(calls, mode="full") -> RunRecord:
    return RunRecord("t", mode, 10, 0, list(calls), [], "", 0, 0, 0.0, 1, None)


def create_call(name, instructions="do the thing"):
    return ToolCall("send_message_to_agent", {"name": name, "instructions": instructions})


def reuse_call(aid, instructions="do the thing"):
    return ToolCall("send_message_to_agent", {"agent_id": aid, "instructions": instructions})


def create_case(required=()) -> Case:
    return Case(id="synthetic", category="new_task_lookalike", split="dev", source="test", severity="normal",
                required_agents=list(required), ia_history=[], message="new thing",
                acceptable=[Outcome("create")])


# ------------------------------------------------------------------ card adapter

def test_card_format_with_contacts_and_active_trigger():
    out = render_full_roster([STANDUP], {})
    assert out == "\n".join([
        '<agent id="ag_standup" name="Standup reminder" last_active="2026-10-29">',
        "description: Reminds the user every day at 8am to post the standup.",
        "contacts: Dana Whitfield <dana@maplerentals.com>",
        "trigger: daily at 8am: Remind the user to post the standup (active)",
        "</agent>",
    ])


def test_cards_keep_roster_order_and_are_joined_by_newline():
    a, b = render_full_roster([STANDUP], {}), render_full_roster([SEARCH], {})
    assert render_full_roster([SEARCH, STANDUP], {}) == b + "\n" + a
    assert render_full_roster([STANDUP, SEARCH], {}) == a + "\n" + b


def test_paused_trigger_is_hidden():
    out = render_full_roster([STANDUP], {})
    assert "timesheet" not in out and "paused" not in out
    assert out.count("trigger:") == 1


def test_schedule_text_is_the_worlds_even_if_describe_schedule_changes(monkeypatch):
    monkeypatch.setattr(roster_view, "describe_schedule", lambda rule, start: "ALTERED")
    out = render_full_roster([STANDUP], {})
    assert "trigger: daily at 8am: Remind the user to post the standup (active)" in out
    assert "ALTERED" not in out


def test_description_override_by_id_and_fallback_to_own():
    out = render_full_roster([STANDUP, SEARCH], {"ag_standup": "Regenerated standup text.",
                                                 "ag_unrelated": "ignored"})
    assert "description: Regenerated standup text." in out
    assert "description: Reminds the user every day" not in out
    assert "description: Searched the inbox for the Air Canada receipt." in out
    assert "ignored" not in out


def test_last_active_from_days_ago():
    agent = AgentDef("ag_x", "X", "d", last_user_activity_days_ago=0.75)  # 18 h before noon
    assert days_ago(0.75).date().isoformat() == "2026-10-31"
    assert 'last_active="2026-10-31"' in render_full_roster([agent], {})
    assert 'last_active="2026-10-29"' in render_full_roster([STANDUP], {})


def test_last_active_falls_back_to_created_at_without_user_activity():
    # AgentDef has no creation time: the adapter's created_at is EVAL_NOW (as regen_descriptions uses).
    agent = AgentDef("ag_x", "X", "d", last_user_activity_days_ago=None)
    assert f'last_active="{EVAL_NOW.date().isoformat()}"' in render_full_roster([agent], {})


def test_empty_roster_is_none():  # Review Focus 5
    assert render_full_roster([], {}) == "None"
    assert render_full_roster([], {"ag_x": "y"}) == "None"


def test_description_coverage():
    assert description_coverage(["a", "b", "c"], {"a": "x", "c": "y", "z": "w"}) == (2, 3)
    assert description_coverage(["a"], {}) == (0, 1)
    assert description_coverage([], {"a": "x"}) == (0, 0)


# ------------------------------------------------------------------ id tool stub

def test_created_agent_id_rule():
    assert created_agent_id(1) == "ag_new00001"
    assert created_agent_id(42) == "ag_new00042"


def test_stub_error_payloads_are_the_production_constants():
    stub = IdToolStub([STANDUP])
    both = stub("send_message_to_agent", {"agent_id": "ag_standup", "name": "x", "instructions": "i"})
    neither = stub("send_message_to_agent", {"instructions": "i"})
    unknown = stub("send_message_to_agent", {"agent_id": "ag_nope", "instructions": "i"})
    assert not (both.success or neither.success or unknown.success)
    assert both.payload == {"error": ia_tools.ERR_BOTH_ID_AND_NAME}
    assert neither.payload == {"error": ia_tools.ERR_NEITHER_ID_NOR_NAME}
    assert unknown.payload == {"error": ia_tools.ERR_UNKNOWN_AGENT_ID.format(agent_id="ag_nope")}
    assert len(stub.calls) == 3


def test_production_tool_returns_the_same_constants(tmp_path, monkeypatch):
    store = AgentStore(tmp_path / "agents.db")
    store.insert_agent(AgentRecord("ag_standup", "Standup reminder", "", EVAL_NOW, None, None))
    monkeypatch.setattr(store_module, "_store", store)

    async def main():
        return (ia_tools.send_message_to_agent("i", agent_id="ag_standup", name="x"),
                ia_tools.send_message_to_agent("i"),
                ia_tools.send_message_to_agent("i", agent_id="ag_nope"))

    both, neither, unknown = asyncio.run(main())
    assert both.payload == {"error": ia_tools.ERR_BOTH_ID_AND_NAME}
    assert neither.payload == {"error": ia_tools.ERR_NEITHER_ID_NOR_NAME}
    assert unknown.payload == {"error": ia_tools.ERR_UNKNOWN_AGENT_ID.format(agent_id="ag_nope")}
    assert [a.id for a in store.list_agents()] == ["ag_standup"]


def test_stub_create_returns_deterministic_ids():
    stub = IdToolStub([STANDUP])
    first = stub("send_message_to_agent", {"name": "Email Alice", "instructions": "a"})
    second = stub("send_message_to_agent", {"name": "Email Alice", "instructions": "b"})
    assert first.success and second.success
    assert first.payload == {"status": "submitted", "agent_id": created_agent_id(1), "new_agent_created": True}
    assert second.payload == {"status": "submitted", "agent_id": created_agent_id(2), "new_agent_created": True}
    assert re.match(NEW_ID_RE, first.payload["agent_id"]) and re.match(NEW_ID_RE, second.payload["agent_id"])


def test_stub_reuse_by_roster_id():
    stub = IdToolStub([STANDUP, SEARCH])
    out = stub("send_message_to_agent", {"agent_id": "ag_search", "instructions": "x"})
    assert out.success
    assert out.payload == {"status": "submitted", "agent_id": "ag_search", "new_agent_created": False}


def test_stub_create_then_dispatch_to_the_returned_id():
    stub = IdToolStub([STANDUP])
    created = stub("send_message_to_agent", {"name": "Email Alice", "instructions": "a"})
    new_id = created.payload["agent_id"]
    again = stub("send_message_to_agent", {"agent_id": new_id, "instructions": "b"})
    assert again.success
    assert again.payload == {"status": "submitted", "agent_id": new_id, "new_agent_created": False}
    # an id the stub did not create is still unknown
    other = stub("send_message_to_agent", {"agent_id": created_agent_id(2), "instructions": "c"})
    assert other.payload == {"error": ia_tools.ERR_UNKNOWN_AGENT_ID.format(agent_id=created_agent_id(2))}


def test_stub_blank_arguments_count_as_absent():  # production's _given rule
    stub = IdToolStub([STANDUP])
    out = stub("send_message_to_agent", {"agent_id": "ag_standup", "name": "  ", "instructions": "x"})
    assert out.payload == {"status": "submitted", "agent_id": "ag_standup", "new_agent_created": False}


def test_stub_missing_instructions_does_not_consume_an_id_and_grader_agrees():  # R-F1-3
    calls = [ToolCall("send_message_to_agent", {"name": "Email Alice"}),
             create_call("Email Alice", "a"),
             reuse_call(created_agent_id(1), "b")]
    stub = IdToolStub([STANDUP])
    results = [stub(c.name, c.args) for c in calls]
    assert not results[0].success and "Missing required arguments" in results[0].payload["error"]
    assert results[1].payload["agent_id"] == created_agent_id(1)
    assert results[2].success
    c = classify(calls, [STANDUP], "full")
    assert len(c.invalid) == 1 and c.invalid[0].startswith("call 0:") and "instructions" in c.invalid[0]
    assert c.created == 1 and c.reused == set()
    assert c.dispatches == [Dispatch("create", "Email Alice", "a\nb")]


def test_stub_unexpected_argument_does_not_consume_an_id_and_grader_agrees():  # R-F1-3
    calls = [ToolCall("send_message_to_agent", {"name": "X", "agent_name": "X", "instructions": "i"}),
             create_call("Email Alice", "a"),
             reuse_call(created_agent_id(1), "b")]
    stub = IdToolStub([STANDUP])
    results = [stub(c.name, c.args) for c in calls]
    assert not results[0].success
    assert results[1].payload["agent_id"] == created_agent_id(1)
    c = classify(calls, [STANDUP], "full")
    assert len(c.invalid) == 1 and c.invalid[0].startswith("call 0:")
    assert c.created == 1 and c.dispatches == [Dispatch("create", "Email Alice", "a\nb")]


def test_stub_other_tools_match_legacy_stub():
    calls = [("send_message_to_user", {"message": "hi"}),
             ("send_draft", {"to": "a@b.io", "subject": "S", "body": "B"}),
             ("wait", {"reason": "already sent"}),
             ("no_such_tool", {}),
             ("send_draft", {"to": "a@b.io"})]
    ids, legacy = IdToolStub([STANDUP]), LegacyToolStub([STANDUP])
    for name, args in calls:
        assert ids(name, args) == legacy(name, args), name
    assert ids.calls == legacy.calls == [ToolCall(n, a) for n, a in calls]


# ------------------------------------------------------------------ grader continuation

def test_dispatch_to_a_created_id_continues_that_create():
    calls = [create_call("Email Khushi", "Email Khushi Shah about the offsite"),
             reuse_call(created_agent_id(1), "and ask about dates")]
    c = classify(calls, [STANDUP], "full")
    assert c.invalid == [] and c.reused == set() and c.created == 1
    assert c.dispatches == [Dispatch("create", "Email Khushi", "Email Khushi Shah about the offsite\nand ask about dates")]
    res = grade(create_case(), record(calls), [STANDUP], "full")
    assert res.passed and res.outcome_kind == "create" and "invalid_call" not in res.flags


def test_continuation_targets_the_right_create():
    calls = [create_call("A", "a"), create_call("B", "b"), reuse_call(created_agent_id(1), "a2")]
    c = classify(calls, [STANDUP], "full")
    assert c.created == 2 and c.invalid == []
    assert c.dispatches == [Dispatch("create", "A", "a\na2"), Dispatch("create", "B", "b")]


def test_truly_unknown_id_is_still_invalid():
    calls = [create_call("A", "a"), reuse_call(created_agent_id(2), "x")]
    c = classify(calls, [STANDUP], "full")
    assert c.created == 1 and len(c.invalid) == 1 and "unknown agent_id" in c.invalid[0]
    res = grade(create_case(), record(calls), [STANDUP], "full")
    assert "invalid_call" in res.flags


def test_created_id_used_before_its_create_is_unknown():
    calls = [reuse_call(created_agent_id(1), "x"), create_call("A", "a")]
    c = classify(calls, [STANDUP], "full")
    assert len(c.invalid) == 1 and c.invalid[0].startswith("call 0:") and "unknown agent_id" in c.invalid[0]
    assert c.created == 1


# ------------------------------------------------------------------ run_case("full")

def test_full_requires_explicit_descriptions():
    with pytest.raises(ValueError, match="descriptions"):
        asyncio.run(run_case(CASES["followup-001"], WORLD, "full", 10, FakeLLM([])))


def test_full_uses_production_prompt_message_and_schemas():
    case = CASES["followup-001"]
    descriptions = {"ag_dana_repair": "REGEN: Dana is sending a technician for the dishwasher."}
    llm = FakeLLM([])
    rec = asyncio.run(run_case(case, WORLD, "full", 10, llm, descriptions=descriptions))
    assert rec.error is None and rec.mode == "full"
    req = llm.requests[0]
    assert req["system"] == ia_agent.build_system_prompt("ids")
    expected = ia_agent.prepare_message_with_history(
        case.message, render_transcript(case.ia_history, "full"), "user",
        roster_block=render_full_roster(roster_for(case, WORLD, 10), descriptions))
    assert req["messages"][0] == expected[0]
    assert "description: REGEN: Dana is sending a technician" in req["messages"][0]["content"]
    assert req["tools"] == ia_tools.TOOL_SCHEMAS


def test_full_reuse_by_id_grades_as_reuse():
    case = CASES["followup-001"]
    llm = FakeLLM([[reuse_call("ag_dana_repair", "Any update from Dana on the dishwasher repair?")]])
    rec = asyncio.run(run_case(case, WORLD, "full", 10, llm, descriptions={}))
    assert rec.error is None
    tool_results = [json.loads(m["content"]) for m in llm.requests[-1]["messages"] if m["role"] == "tool"]
    assert tool_results[0]["result"] == {"status": "submitted", "agent_id": "ag_dana_repair",
                                         "new_agent_created": False}
    res = grade(case, rec, roster_for(case, WORLD, 10), "full")
    assert res.passed and res.outcome_kind == "reuse"


def test_full_create_by_name_grades_as_create():
    case = CASES["newtask-001"]
    llm = FakeLLM([[create_call("Email Dana re painting", "Ask Dana Whitfield whether I can paint the bedroom")]])
    rec = asyncio.run(run_case(case, WORLD, "full", 10, llm, descriptions={}))
    assert rec.error is None
    tool_results = [json.loads(m["content"]) for m in llm.requests[-1]["messages"] if m["role"] == "tool"]
    assert tool_results[0]["result"] == {"status": "submitted", "agent_id": created_agent_id(1),
                                         "new_agent_created": True}
    res = grade(case, rec, roster_for(case, WORLD, 10), "full")
    assert res.passed and res.outcome_kind == "create"


def test_name_modes_ignore_descriptions():
    case = CASES["followup-001"]
    plain, given = FakeLLM([]), FakeLLM([])
    asyncio.run(run_case(case, WORLD, "legacy", 10, plain))
    asyncio.run(run_case(case, WORLD, "legacy", 10, given, descriptions={"ag_dana_repair": "REGEN"}))
    assert plain.requests[0]["messages"] == given.requests[0]["messages"]
    assert plain.requests[0]["system"] == given.requests[0]["system"]


# ------------------------------------------------------------------ runner / CLI

class PerConversationFake:
    """A fresh text-only FakeLLM per conversation; records every request."""

    def __init__(self):
        self.requests = []
        self._convs = {}

    async def __call__(self, **kwargs):
        self.requests.append(kwargs)
        conv = self._convs.setdefault(id(kwargs["messages"]), FakeLLM([]))
        return await conv(**kwargs)


def config(**kw):
    base = dict(modes=["full"], sizes=[10], split="dev", runs=1, model=HAIKU, case_ids=THREE,
                max_cost=35.0, purpose="fake full run", concurrency=2,
                command="python -m evals.run routing --modes full --sizes 10 --split dev")
    base.update(kw)
    return rr.RoutingConfig(**base)


def write_regen(path: Path, descriptions) -> Path:
    path.write_text(json.dumps({"model": "m", "generated_on": "2026-11-07", "descriptions": descriptions}),
                    encoding="utf-8")
    return path


@pytest.fixture
def regen_path(tmp_path, monkeypatch):
    path = tmp_path / "descriptions.regen.json"
    monkeypatch.setattr(rd, "OUT_PATH", path)
    return path


def test_full_is_a_mode_runner():
    assert rr.MODE_RUNNERS["full"] is routing.run_case


@pytest.mark.parametrize("content", [None, "not json {", json.dumps({"model": "m", "descriptions": {}}),
                                     json.dumps({"model": "m"})])
def test_bad_regen_file_is_a_clear_error(regen_path, content):
    if content is not None:
        regen_path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        rr.load_descriptions(regen_path)
    assert str(regen_path) in str(exc.value) and RUN_HINT in str(exc.value)


def test_full_run_with_bad_regen_file_fails_before_spending(tmp_path, regen_path):
    llm = PerConversationFake()
    cases = rr.load_run_cases(config(), CASES_DIR)
    with pytest.raises(ValueError, match="regen-descriptions"):
        asyncio.run(rr.execute_routing(config(), cases, WORLD, llm, tmp_path / "results"))
    assert llm.requests == []
    assert not (tmp_path / "results").exists()


def test_cli_full_with_missing_regen_file_returns_nonzero_before_estimate(tmp_path, regen_path, capsys):
    out_root = tmp_path / "results"
    rc = run_mod.main(["routing", "--modes", "full", "--sizes", "10", "--split", "dev", "--yes",
                       "--out-root", str(out_root)])
    out = capsys.readouterr().out
    assert rc != 0
    assert str(regen_path) in out and RUN_HINT in out
    assert "estimated cost" not in out.lower()
    assert not out_root.exists()


def test_cli_full_estimate_prints_and_nothing_runs_without_yes(tmp_path, regen_path, capsys, monkeypatch):
    write_regen(regen_path, {"ag_x": "y"})
    fake = FakeLLM.text("never")
    monkeypatch.setattr(rr, "default_llm", lambda: fake)
    out_root = tmp_path / "results"
    rc = run_mod.main(["routing", "--modes", "full", "--sizes", "10", "--split", "dev",
                       "--out-root", str(out_root)])
    out = capsys.readouterr().out
    assert rc == 2 and "estimated cost" in out.lower() and "--yes" in out
    assert "16 case-runs" in out
    assert fake.requests == [] and not out_root.exists()  # no case-run started, no run folder


def test_cli_descriptions_world_needs_no_regen_file(tmp_path, regen_path, capsys):
    rc = run_mod.main(["routing", "--modes", "full", "--sizes", "10", "--split", "dev",
                       "--descriptions", "world", "--out-root", str(tmp_path / "results")])
    out = capsys.readouterr().out
    assert rc == 2 and "estimated cost" in out.lower()


def test_cli_name_modes_ignore_a_missing_regen_file(tmp_path, regen_path, capsys):
    rc = run_mod.main(["routing", "--modes", "legacy", "--sizes", "10", "--split", "dev", "--descriptions", "regen",
                       "--out-root", str(tmp_path / "results")])
    out = capsys.readouterr().out
    assert rc == 2 and "estimated cost" in out.lower() and RUN_HINT not in out


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_full_run_uses_regen_descriptions_and_records_source_sha_and_coverage(tmp_path, regen_path, monkeypatch):
    cfg = config(descriptions="regen")
    cases = rr.load_run_cases(cfg, CASES_DIR)
    target = cases[0].required_agents[0].id
    world_ids = sorted(WORLD.agents)
    marker = "REGEN-MARKER: regenerated card text."
    write_regen(regen_path, {target: marker, world_ids[0]: "x", "ag_not_in_world": "z"})
    covered = len({target, world_ids[0]} & set(WORLD.agents))
    loads = []
    real_load = rr.load_descriptions

    def counting_load(*args, **kwargs):
        loads.append(args)
        return real_load(*args, **kwargs)

    monkeypatch.setattr(rr, "load_descriptions", counting_load)
    llm = PerConversationFake()
    run_dir = asyncio.run(rr.execute_routing(cfg, cases, WORLD, llm, tmp_path / "results"))
    assert len(loads) == 1  # once per run, not per case-run
    assert any(marker in r["messages"][0]["content"] for r in llm.requests)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["descriptions"] == {"source": "regen", "sha256": _sha(regen_path),
                                       "covered": covered, "total": len(WORLD.agents)}
    report = (run_dir / "report.md").read_text()
    assert "regen" in report and _sha(regen_path) in report and f"{covered}/{len(WORLD.agents)}" in report
    records = [json.loads(line) for line in (run_dir / "records.jsonl").read_text().splitlines() if line.strip()]
    assert {r["mode"] for r in records} == {"full"} and len(records) == 3


def test_full_run_with_world_descriptions(tmp_path, regen_path):
    cfg = config(descriptions="world")
    cases = rr.load_run_cases(cfg, CASES_DIR)
    llm = PerConversationFake()
    run_dir = asyncio.run(rr.execute_routing(cfg, cases, WORLD, llm, tmp_path / "results"))
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["descriptions"]["source"] == "world" and summary["descriptions"]["sha256"] is None
    own = cases[0].required_agents[0].description
    assert any(f"description: {own}" in r["messages"][0]["content"] for r in llm.requests)


# Task 14: descriptions serve hybrid too, with a generic error ------------------------------------

def test_load_descriptions_error_is_not_full_specific(regen_path):
    with pytest.raises(ValueError) as exc:
        rr.load_descriptions(regen_path)
    assert "needs regenerated descriptions" in str(exc.value) and "'full'" not in str(exc.value)


def test_hybrid_run_uses_regen_descriptions(tmp_path, regen_path):
    cfg = config(modes=["hybrid"], descriptions="regen", embedder="hashing")
    cases = rr.load_run_cases(cfg, CASES_DIR)
    target = cases[0].required_agents[0].id
    marker = "REGEN-MARKER: regenerated card text."
    write_regen(regen_path, {target: marker})
    llm = PerConversationFake()
    run_dir = asyncio.run(rr.execute_routing(cfg, cases, WORLD, llm, tmp_path / "results"))
    assert any(marker in r["messages"][0]["content"] for r in llm.requests)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["descriptions"]["source"] == "regen"


def test_hybrid_run_with_bad_regen_file_fails_before_spending(tmp_path, regen_path):
    llm = PerConversationFake()
    cfg = config(modes=["hybrid"], descriptions="regen", embedder="hashing")
    cases = rr.load_run_cases(cfg, CASES_DIR)
    with pytest.raises(ValueError, match="regen-descriptions"):
        asyncio.run(rr.execute_routing(cfg, cases, WORLD, llm, tmp_path / "results"))
    assert llm.requests == [] and not (tmp_path / "results").exists()
