"""The ``routing`` runner: frozen cases -> real IA loop (FakeLLM here) -> grades -> run folder."""
import asyncio
import json
import shutil
from pathlib import Path

import pytest

from evals import routing_run as rr
from evals import run as run_mod
from evals.caseset import V1_DIR, CaseSetError
from evals.grading import ToolCall
from evals.harness.fake_llm import FakeLLM
from evals.harness.routing import run_case
from evals.pricing import HAIKU, SONNET
from evals.world.roster import load_world
from server.agents.execution_agent.batch_manager import ExecutionBatchManager
from server.agents.interaction_agent import runtime as ia_runtime
from server.agents.interaction_agent import tools as ia_tools
from server.openrouter_client import OpenRouterError

CASES_DIR = Path("evals/cases/v1")
WORLD = load_world(Path("evals/world/world.json"))
SECRET = "sk-or-v1-THIS-IS-A-TEST-SECRET-0123456789"

# Scripts keyed by a substring of each case's current message.
SCRIPTS = {
    "Farah Moreau mention": [[ToolCall("send_message_to_agent",
                                       {"agent_name": "Email Farah the transcript", "instructions": "Ask Farah Moreau about the write-up"})]],
    "Daniel gotten back": [[ToolCall("send_message_to_user", {"message": "Which Daniel do you mean?"})]],
    # Two roster agents share this name: a structural failure under legacy.
    "Sam Okafor": [[ToolCall("send_message_to_agent",
                             {"agent_name": "Email Sam re vendor contract", "instructions": "Email Sam Okafor"})]],
}
THREE = ["clear-person-005", "amb-person-006", "newtask-005"]


class RoutedFake:
    """One scripted FakeLLM per conversation, chosen by the case message; records every request."""

    def __init__(self, scripts=SCRIPTS, *, fail=None, flaky=None, prompt_tokens=FakeLLM.PROMPT_TOKENS):
        self.scripts = scripts
        self.fail = fail or set()      # substrings whose conversations always raise
        self.flaky = set(flaky or ())  # substrings that raise once, then work
        self.prompt_tokens = prompt_tokens
        self.requests = []
        self._convs = {}

    async def __call__(self, **kwargs):
        self.requests.append(kwargs)
        content = kwargs["messages"][0]["content"]
        key = next((k for k in self.scripts if k in content), None)
        if any(k in content for k in self.fail):
            raise OpenRouterError("OpenRouter request failed (502): upstream")
        for k in list(self.flaky):
            if k in content:
                self.flaky.discard(k)
                raise OpenRouterError("OpenRouter request failed: timed out")
        conv = self._convs.setdefault(id(kwargs["messages"]), FakeLLM(self.scripts.get(key, [])))
        conv.PROMPT_TOKENS = self.prompt_tokens
        return await conv(**kwargs)


@pytest.fixture(autouse=True)
def _no_production_side_effects(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("runner reached production code")

    async def aboom(*args, **kwargs):
        raise AssertionError("runner reached production code")

    monkeypatch.setattr(ia_runtime, "handle_tool_call", boom)
    monkeypatch.setattr(ia_tools, "handle_tool_call", boom)
    monkeypatch.setattr(ia_runtime, "request_chat_completion", aboom)
    monkeypatch.setattr(ExecutionBatchManager, "execute_agent", aboom)
    monkeypatch.setattr(rr, "default_llm", aboom)


def config(**kw):
    base = dict(modes=["legacy"], sizes=[10, 30], split="dev", runs=1, model=HAIKU, case_ids=THREE,
                max_cost=35.0, purpose="fake legacy run", concurrency=4,
                command="python -m evals.run routing --modes legacy --sizes 10,30 --split dev")
    base.update(kw)
    return rr.RoutingConfig(**base)


def execute(tmp_path, cfg=None, llm=None, **kw):
    cfg = cfg or config()
    llm = llm or RoutedFake()
    cases = rr.load_run_cases(cfg, CASES_DIR)
    run_dir = asyncio.run(rr.execute_routing(cfg, cases, WORLD, llm, tmp_path / "results", cases_dir=V1_DIR, **kw))
    return run_dir, llm


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_end_to_end_writes_every_output_file(tmp_path):
    run_dir, llm = execute(tmp_path)
    assert run_dir.parent == tmp_path / "results"
    assert run_dir.name.endswith("-fake-legacy-run")
    for name in ["records.jsonl", "grades.jsonl", "errors.jsonl", "summary.json", "report.md"]:
        assert (run_dir / name).exists(), name
    records, grades = jsonl(run_dir / "records.jsonl"), jsonl(run_dir / "grades.jsonl")
    assert jsonl(run_dir / "errors.jsonl") == []
    # deterministic order: cases sorted by id, then mode, size, run
    order = [(r["case_id"], r["mode"], r["n"], r["run_idx"]) for r in records]
    assert order == [(c, "legacy", n, 0) for c in sorted(THREE) for n in (10, 30)]
    assert [(g["case_id"], g["n"]) for g in grades] == [(c, n) for c, _, n, _ in order]
    assert all(r["model"] == HAIKU for r in records)
    assert records[0]["calls"] and set(records[0]["calls"][0]) == {"name", "args"}
    transcripts = sorted(p.name for p in (run_dir / "transcripts").iterdir())
    assert transcripts == sorted(f"{c}-legacy-{n}-0.json" for c, _, n, _ in order)
    t = json.loads((run_dir / "transcripts" / "clear-person-005-legacy-10-0.json").read_text())
    assert t["messages"][0]["role"] == "system"
    assert [m["role"] for m in t["messages"][1:]] == ["user", "assistant", "tool", "assistant"]

    by = {(g["case_id"], g["n"]): g for g in grades}
    assert by[("clear-person-005", 10)]["passed"] and by[("clear-person-005", 30)]["passed"]
    assert by[("newtask-005", 10)]["structural"] and not by[("newtask-005", 10)]["passed"]
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["counts"]["planned"] == 6 and summary["counts"]["graded"] == 6
    assert summary["counts"]["infra_errors"] == 0 and summary["counts"]["skipped_max_cost"] == 0
    cell = summary["pass_rate"]["legacy"]["10"]
    assert cell["graded"] == 3 and cell["passed"] == by_count(grades, 10)
    assert summary["structural"]["legacy"]["10"] == 1
    assert summary["case_set"]["frozen_on"] == "2026-11-07" and len(summary["case_set"]["manifest_sha256"]) == 64
    assert summary["cost"]["prompt_tokens"] == sum(r["prompt_tokens"] for r in records)
    assert summary["cost"]["actual_usd"] > 0


def by_count(grades, n):
    return sum(g["passed"] for g in grades if g["n"] == n)


def test_records_are_ordered_even_with_concurrency(tmp_path):
    a, _ = execute(tmp_path / "a", config(concurrency=1))
    b, _ = execute(tmp_path / "b", config(concurrency=6))
    strip = lambda rows: [{k: v for k, v in r.items() if k != "latency_s"} for r in rows]  # noqa: E731
    assert strip(jsonl(a / "records.jsonl")) == strip(jsonl(b / "records.jsonl"))


def test_infra_error_is_retried_once_then_lands_in_errors_and_is_not_graded(tmp_path):
    llm = RoutedFake(fail={"Daniel gotten back"}, flaky={"Farah Moreau mention"})
    run_dir, _ = execute(tmp_path, config(sizes=[10]), llm)
    errors = jsonl(run_dir / "errors.jsonl")
    assert [(e["case_id"], e["n"]) for e in errors] == [("amb-person-006", 10)]
    assert errors[0]["attempts"] == 2 and len(errors[0]["attempt_errors"]) == 2
    assert all("OpenRouterError" in e for e in errors[0]["attempt_errors"])
    daniel = [r for r in llm.requests if "Daniel gotten back" in r["messages"][0]["content"]]
    assert len(daniel) == 2  # first try + exactly one retry
    grades = jsonl(run_dir / "grades.jsonl")
    assert {g["case_id"] for g in grades} == {"clear-person-005", "newtask-005"}
    records = jsonl(run_dir / "records.jsonl")
    farah = next(r for r in records if r["case_id"] == "clear-person-005")
    assert farah["attempts"] == 2 and farah["error"] is None
    assert all(r["case_id"] != "amb-person-006" for r in records)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["counts"]["infra_errors"] == 1 and summary["counts"]["retried"] == 2
    assert summary["pass_rate"]["legacy"]["10"]["graded"] == 2  # the error is excluded
    assert summary["infra_errors"]["legacy"]["10"] == 1


def test_max_cost_cap_stops_further_case_runs(tmp_path):
    llm = RoutedFake(prompt_tokens=5000)
    one_run = rr.reservation_usd(HAIKU, "legacy", 10)  # what the cap reserves per case-run
    # actual cost of one fake case-run: 2 calls x (5000 prompt + 20 completion)
    actual = 2 * (5000 * 0.10 + 20 * 0.50) / 1e6
    cap = 2 * actual + one_run - 1e-9  # room for exactly two case-runs
    run_dir, _ = execute(tmp_path, config(sizes=[10], max_cost=cap, concurrency=1), llm)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["counts"]["completed"] == 2 and summary["counts"]["skipped_max_cost"] == 1
    assert summary["cost"]["actual_usd"] <= cap
    assert len(jsonl(run_dir / "records.jsonl")) == 2
    assert "skipped" in (run_dir / "report.md").read_text().lower()


def test_routing_without_yes_prints_estimate_and_refuses(tmp_path, capsys):
    out_root = tmp_path / "results"
    rc = run_mod.main(["routing", "--modes", "legacy", "--sizes", "10,300", "--split", "dev",
                       "--out-root", str(out_root)])
    out = capsys.readouterr().out
    assert rc == 2 and "estimated cost" in out.lower() and "--yes" in out
    assert "32 case-runs" in out  # 16 dev cases x 2 sizes x 1 run
    assert not out_root.exists()


def test_routing_with_yes_runs_through_cli(tmp_path, capsys, monkeypatch):
    llm = RoutedFake()
    monkeypatch.setattr(rr, "default_llm", lambda: llm)
    monkeypatch.setattr(rr, "configured_api_key", lambda: SECRET)
    out_root = tmp_path / "results"
    rc = run_mod.main(["routing", "--modes", "legacy", "--sizes", "10", "--split", "dev",
                       "--cases", ",".join(THREE), "--yes", "--purpose", "cli smoke",
                       "--out-root", str(out_root)])
    out = capsys.readouterr().out
    assert rc == 0, out
    (run_dir,) = [p for p in out_root.iterdir() if p.is_dir()]
    report = (run_dir / "report.md").read_text()
    assert "--purpose 'cli smoke'" in report and "--yes" in report
    assert all(r["api_key"] == SECRET for r in llm.requests)
    assert all(r["model"] == HAIKU for r in llm.requests)


def test_api_key_never_written(tmp_path):
    run_dir, llm = execute(tmp_path, api_key=SECRET)
    assert llm.requests and all(r["api_key"] == SECRET for r in llm.requests)
    files = [p for p in (tmp_path / "results").rglob("*") if p.is_file()]
    assert len(files) > 8
    for p in files:
        text = p.read_text()
        assert SECRET not in text, p
        assert "api_key" not in text and "Authorization" not in text, p


def test_model_override_reaches_llm_kwargs(tmp_path, monkeypatch):
    from server.config import get_settings
    assert get_settings().interaction_agent_model != HAIKU
    _, llm = execute(tmp_path, config(model=HAIKU))
    assert {r["model"] for r in llm.requests} == {HAIKU}
    _, llm = execute(tmp_path, config(model=SONNET))
    assert {r["model"] for r in llm.requests} == {SONNET}


def test_unpriced_model_is_rejected():
    with pytest.raises(ValueError, match="no price"):
        rr.estimate(config(model="openai/gpt-unknown"), [])


def _copy_cases(tmp_path):
    dst = tmp_path / "cases"
    shutil.copytree(CASES_DIR, dst)
    return dst


def test_tampered_case_dir_is_refused(tmp_path, capsys):
    d = _copy_cases(tmp_path)
    p = d / "clear-person-005.json"
    p.write_text(p.read_text().replace("Farah Moreau mention", "Farah Moreau say"))
    with pytest.raises(CaseSetError, match="modified"):
        rr.load_run_cases(config(), d)
    rc = run_mod.main(["routing", "--modes", "legacy", "--sizes", "10", "--cases-dir", str(d),
                       "--out-root", str(tmp_path / "r")])
    assert rc == 1 and "rejected" in capsys.readouterr().out


def test_unfrozen_case_dir_is_refused(tmp_path):
    d = _copy_cases(tmp_path)
    m = json.loads((d / "MANIFEST.json").read_text())
    m["frozen"] = False
    (d / "MANIFEST.json").write_text(json.dumps(m))
    with pytest.raises(CaseSetError, match="not frozen"):
        rr.load_run_cases(config(), d)


def test_split_and_case_filters():
    dev = rr.load_run_cases(config(case_ids=None), CASES_DIR)
    assert len(dev) == 16 and {c.split for c in dev} == {"dev"}
    assert len(rr.load_run_cases(config(case_ids=None, split="test"), CASES_DIR)) == 33
    assert len(rr.load_run_cases(config(case_ids=None, split="all"), CASES_DIR)) == 49
    with pytest.raises(ValueError, match="not in split"):
        rr.load_run_cases(config(case_ids=["amb-person-001"]), CASES_DIR)  # a test case


def test_unimplemented_mode_is_a_clear_error(tmp_path, capsys):
    with pytest.raises(ValueError, match="not implemented yet"):
        execute(tmp_path, config(modes=["legacy", "recency"]))
    rc = run_mod.main(["routing", "--modes", "recency", "--sizes", "10", "--out-root", str(tmp_path / "r")])
    assert rc == 1 and "not implemented yet" in capsys.readouterr().out


def test_adaptive_is_not_a_mode():
    from evals.grading import EVAL_MODES, ROSTER_MODES
    from evals.harness.render import render_transcript

    assert "adaptive" not in ROSTER_MODES and "adaptive" not in EVAL_MODES
    assert "adaptive" not in rr.PROMPT_TOKENS_PER_CASE_RUN
    with pytest.raises(ValueError, match="unknown roster mode"):
        render_transcript([], "adaptive")


def test_estimate_is_calibrated_per_case_run_from_experiment_1():
    # Experiment 1 (legacy, Haiku, dev): N=10 ~11.9k and N=300 ~20.3k prompt tokens per case-run.
    assert rr.prompt_tokens_per_case_run("legacy", 10) == 11900
    assert rr.prompt_tokens_per_case_run("legacy", 300) == 20300
    assert rr.prompt_tokens_per_case_run("legacy", 30) == round(11900 + 8400 * 20 / 290)
    assert rr.prompt_tokens_per_case_run("legacy", 100) == round(11900 + 8400 * 90 / 290)
    assert rr.COMPLETION_TOKENS_PER_CASE_RUN == 600
    # other modes: the rough table scaled by the measured/estimated ratio (provisional)
    # full: measured in experiment 5 (Haiku, dev)
    assert [rr.prompt_tokens_per_case_run("full", n) for n in (10, 30, 100, 300)] == [18009, 24936, 51878, 117473]
    assert rr.prompt_tokens_per_case_run("full", 300) == 117473
    # hybrid: the full estimate at min(N, 20) x 1.1 (measured ~x1.00-1.03 in the Task 14 smoke, plus headroom)
    for n in (10, 30, 100, 300):
        assert rr.prompt_tokens_per_case_run("hybrid", n) == round(
            rr.prompt_tokens_per_case_run("full", min(n, 20)) * 1.1)
    assert rr.prompt_tokens_per_case_run("hybrid", 10) == 19810
    assert rr.HYBRID_SEARCH_FACTOR == pytest.approx(1.1)
    assert rr.prompt_tokens_per_case_run("hybrid", 30) == rr.prompt_tokens_per_case_run("hybrid", 300)
    assert rr.MEASURED_OVER_ESTIMATED == pytest.approx(1.6)
    cfg = config(sizes=[10, 300], case_ids=None)
    est = rr.estimate(cfg, rr.load_run_cases(cfg, CASES_DIR))
    assert est.case_runs == 32
    assert est.prompt_tokens == 16 * (11900 + 20300) and est.completion_tokens == 32 * 600
    assert est.usd == pytest.approx(16 * (rr.estimate_case_run_cost(HAIKU, "legacy", 10)
                                          + rr.estimate_case_run_cost(HAIKU, "legacy", 300)))
    # experiment 1 cost $0.0610; the calibrated estimate lands near it
    assert 0.055 < est.usd < 0.07


def test_cap_reserves_the_estimate_with_a_safety_margin():
    assert rr.RESERVATION_MARGIN == 1.2
    assert rr.reservation_usd(HAIKU, "legacy", 10) == pytest.approx(1.2 * rr.estimate_case_run_cost(HAIKU, "legacy", 10))
    ledger = rr._Ledger(HAIKU, max_cost=1.0)
    assert ledger.try_reserve(0.6) and not ledger.try_reserve(0.6)


def test_report_has_expected_sections_and_experiments_gets_one_line(tmp_path):
    run_dir, _ = execute(tmp_path)
    report = (run_dir / "report.md").read_text()
    for heading in ["# Routing run", "## Setup", "## Cost", "## Pass rate by mode × N", "## Pass rate by category",
                    "## Flags", "## Structural failures", "## Infra errors", "## Failing case-runs",
                    "## What we learned"]:
        assert heading in report, heading
    assert "fake legacy run" in report and "uncommitted working tree" in report
    assert "newtask-005" in report  # a failing case with its reason
    assert report.rstrip().endswith("## What we learned")
    exp = tmp_path / "results" / "EXPERIMENTS.md"
    lines = exp.read_text().splitlines()
    rows = [line for line in lines if run_dir.name in line]
    assert len(rows) == 1 and "fake legacy run" in rows[0] and "$" in rows[0]
    run_dir2, _ = execute(tmp_path, config(purpose="second"))
    lines2 = exp.read_text().splitlines()
    assert len(lines2) == len(lines) + 1 and run_dir2.name in lines2[-1]


def test_timeout_is_an_infra_error_and_its_spend_is_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "ATTEMPT_TIMEOUT_S", 0.2)

    class SlowSecondCall(RoutedFake):
        async def __call__(self, **kwargs):
            if len(kwargs["messages"]) > 1:  # after the first response: hang
                await asyncio.sleep(5)
            return await super().__call__(**kwargs)

    run_dir, llm = execute(tmp_path, config(sizes=[10], case_ids=["clear-person-005"]), SlowSecondCall())
    (err,) = jsonl(run_dir / "errors.jsonl")
    assert err["attempts"] == 2 and all(e.startswith("TimeoutError") for e in err["attempt_errors"])
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["cost"]["prompt_tokens"] == 2 * FakeLLM.PROMPT_TOKENS  # one answered call per attempt
    assert summary["counts"]["graded"] == 0


# ---------------------------------------------------------------- robustness (Milestone A follow-up)

class Abort(BaseException):
    """Escapes every ``except Exception``: stands in for a crash or Ctrl-C in the middle of a run."""


def test_completed_case_runs_are_on_disk_before_the_run_ends(tmp_path):
    seen = []

    async def runner(case, world, mode, n, llm, run_idx=0):
        seen.append(case.id)
        if len(seen) == 3:
            raise Abort()
        return await run_case(case, world, mode, n, llm, run_idx)

    with pytest.raises(Abort):
        execute(tmp_path, config(sizes=[10], concurrency=1), runners={"legacy": runner})
    (run_dir,) = list((tmp_path / "results").iterdir())
    records = jsonl(run_dir / "records.jsonl")
    assert sorted(r["case_id"] for r in records) == sorted(seen[:2])
    assert len(jsonl(run_dir / "grades.jsonl")) == 2
    assert sorted(p.name for p in (run_dir / "transcripts").iterdir()) == sorted(f"{c}-legacy-10-0.json" for c in seen[:2])


def test_an_exception_in_one_case_run_becomes_a_runner_error(tmp_path):
    async def runner(case, world, mode, n, llm, run_idx=0):
        if case.id == "amb-person-006":
            raise ValueError("roster size 10 is smaller than the 12 required agents")
        return await run_case(case, world, mode, n, llm, run_idx)

    run_dir, _ = execute(tmp_path, config(sizes=[10]), runners={"legacy": runner})
    (err,) = jsonl(run_dir / "errors.jsonl")
    assert err["case_id"] == "amb-person-006" and err["error"].startswith("RunnerError: ValueError")
    assert {g["case_id"] for g in jsonl(run_dir / "grades.jsonl")} == {"clear-person-005", "newtask-005"}
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["counts"]["infra_errors"] == 1 and summary["error_kinds"] == {"RunnerError": 1}
    assert (run_dir / "transcripts" / "amb-person-006-legacy-10-0.json").exists()


def test_a_grading_exception_becomes_a_runner_error_for_that_record_only(tmp_path, monkeypatch):
    real = rr.grade

    def flaky_grade(case, record, roster, mode):
        if case.id == "newtask-005":
            raise KeyError("boom")
        return real(case, record, roster, mode)

    monkeypatch.setattr(rr, "grade", flaky_grade)
    run_dir, _ = execute(tmp_path, config(sizes=[10]))
    (err,) = jsonl(run_dir / "errors.jsonl")
    assert err["case_id"] == "newtask-005" and err["error"].startswith("RunnerError: grading failed: KeyError")
    assert err["calls"]  # the paid record is kept
    assert len(jsonl(run_dir / "grades.jsonl")) == 2


class NoUsage(RoutedFake):
    async def __call__(self, **kwargs):
        response = await super().__call__(**kwargs)
        response.pop("usage")
        return response


def test_a_response_without_usage_charges_the_estimate(tmp_path):
    with pytest.warns(RuntimeWarning, match="no usage"):
        run_dir, _ = execute(tmp_path, config(sizes=[10], case_ids=["clear-person-005"]), NoUsage())
    summary = json.loads((run_dir / "summary.json").read_text())
    est = rr.estimate_case_run_cost(HAIKU, "legacy", 10)
    assert summary["cost"]["prompt_tokens"] == 0
    assert summary["cost"]["actual_usd"] == pytest.approx(est)
    assert summary["cost"]["unmetered_attempts"] == 1
    assert "no usage" in (run_dir / "report.md").read_text()


def test_a_response_without_usage_still_stops_the_cap(tmp_path):
    cap = 2.5 * rr.reservation_usd(HAIKU, "legacy", 10)
    with pytest.warns(RuntimeWarning):
        run_dir, _ = execute(tmp_path, config(sizes=[10], max_cost=cap, concurrency=1), NoUsage())
    c = json.loads((run_dir / "summary.json").read_text())["counts"]
    assert c["completed"] == 2 and c["skipped_max_cost"] == 1


@pytest.mark.parametrize("error, kind", [
    ("OpenRouterError: OpenRouter request failed (502): upstream", "OpenRouterError"),
    ("TimeoutError: no final response within 300s", "Timeout"),
    ("MalformedToolCall: 1 of 2 tool calls had no name or invalid arguments", "MalformedToolCall"),
    ("RuntimeError: Reached tool iteration limit without final response", "IterationLimit"),
    ("RunnerError: ValueError: x", "RunnerError"),
    ("weird", "Other"),
])
def test_error_kind(error, kind):
    from evals.run_store import error_kind
    assert error_kind(error) == kind


def test_report_tallies_errors_by_kind_and_names_iteration_limit_loops(tmp_path):
    async def runner(case, world, mode, n, llm, run_idx=0):
        rec = await run_case(case, world, mode, n, llm, run_idx)
        if case.id == "newtask-005":
            from dataclasses import replace as _r
            return _r(rec, error="RuntimeError: Reached tool iteration limit without final response")
        return rec

    llm = RoutedFake(fail={"Daniel gotten back"})
    run_dir, _ = execute(tmp_path, config(sizes=[10]), llm, runners={"legacy": runner})
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["error_kinds"] == {"IterationLimit": 1, "OpenRouterError": 1}
    assert summary["iteration_limit"] == ["newtask-005 legacy N=10 run 0"]
    report = (run_dir / "report.md").read_text()
    assert "| OpenRouterError | 1 |" in report and "| IterationLimit | 1 |" in report
    assert "iteration limit" in report.lower() and "upward" in report and "newtask-005" in report


def test_summary_records_the_world_sha(tmp_path):
    from evals.caseset import sha256_file
    run_dir, _ = execute(tmp_path, config(sizes=[10], case_ids=["clear-person-005"]))
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["case_set"]["world_sha256"] == sha256_file(Path("evals/world/world.json"))


# Task 14: hybrid through the runner ---------------------------------------------------------------

def test_hybrid_is_a_mode_runner_and_the_module_doc_no_longer_says_otherwise():
    assert rr.MODE_RUNNERS["hybrid"] is run_case
    assert "hybrid not implemented" not in rr.__doc__.lower() and "recency" not in rr.__doc__.lower()


def test_make_embedder_hashing_is_cached_and_unknown_is_an_error():
    from evals.harness.load_world import CachedEmbedder

    assert isinstance(rr.make_embedder("hashing"), CachedEmbedder)
    with pytest.raises(ValueError, match="embedder"):
        rr.make_embedder("nope")


def test_cli_embedder_flag_defaults_to_fastembed(tmp_path, monkeypatch, capsys):
    seen = []
    real = rr.estimate
    monkeypatch.setattr(rr, "estimate", lambda cfg, cases: seen.append(cfg.embedder) or real(cfg, cases))
    base = ["routing", "--modes", "hybrid", "--sizes", "10", "--descriptions", "world", "--out-root", str(tmp_path / "r")]
    assert run_mod.main(base) == 2
    assert run_mod.main([*base, "--embedder", "hashing"]) == 2
    assert seen == ["fastembed", "hashing"]
    with pytest.raises(SystemExit):
        run_mod.main([*base, "--embedder", "nope"])
    capsys.readouterr()


class SearchingFake:
    """Every conversation searches once with a fixed query, then answers with text."""

    def __init__(self):
        self.requests = []
        self._convs = {}

    async def __call__(self, **kwargs):
        self.requests.append(kwargs)
        conv = self._convs.setdefault(id(kwargs["messages"]),
                                      FakeLLM([[ToolCall("search_agents", {"query": "invoice"})]]))
        return await conv(**kwargs)


def hybrid_config(**kw):
    base = dict(modes=["hybrid"], sizes=[10, 30], descriptions="world", embedder="hashing",
                purpose="fake hybrid run")
    return config(**{**base, **kw})


def test_hybrid_run_records_embedder_searches_and_descriptions(tmp_path):
    cfg = hybrid_config()
    run_dir, llm = execute(tmp_path, cfg, SearchingFake())
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["embedder"] == "hashing"
    records = jsonl(run_dir / "records.jsonl")
    assert len(records) == 6 and jsonl(run_dir / "errors.jsonl") == []
    assert all(r["searches"] and r["searches"][0]["query"] == "invoice" for r in records)
    assert all(len(r["initial_ids"]) == r["n"] if r["n"] <= 20 else len(r["initial_ids"]) == 20 for r in records)
    cases = rr.load_run_cases(cfg, CASES_DIR)
    own = cases[0].required_agents[0].description
    assert any(f"description: {own}" in r["messages"][0]["content"] for r in llm.requests)  # descriptions reach hybrid


def test_legacy_run_summary_has_no_embedder(tmp_path):
    run_dir, _ = execute(tmp_path)
    assert "embedder" not in json.loads((run_dir / "summary.json").read_text())


def test_report_has_search_rate_and_error_columns_for_hybrid_only(tmp_path):
    run_dir, _ = execute(tmp_path, hybrid_config(), SearchingFake())
    summary = json.loads((run_dir / "summary.json").read_text())
    for n in ("10", "30"):
        cell = summary["search"]["hybrid"][n]
        assert cell["graded"] == 3 and cell["searched"] == 3 and cell["search_errors"] == 0
        assert {"target_in_initial", "target_found_by_search"} <= set(cell)
    assert summary["search"]["hybrid"]["10"]["target_found_by_search"] == 0  # all 10 agents are shown
    report = (run_dir / "report.md").read_text()
    assert "## Search" in report and "Search rate" in report and "Search errors" in report
    legacy_dir, _ = execute(tmp_path / "other")
    assert "Search rate" not in (legacy_dir / "report.md").read_text()


def test_hybrid_search_errors_are_counted(tmp_path):
    class DoubleSearch(SearchingFake):
        async def __call__(self, **kwargs):
            self.requests.append(kwargs)
            conv = self._convs.setdefault(id(kwargs["messages"]), FakeLLM(
                [[ToolCall("search_agents", {"query": "invoice"})], [ToolCall("search_agents", {"query": "again"})]]))
            return await conv(**kwargs)

    run_dir, _ = execute(tmp_path, hybrid_config(sizes=[10]), DoubleSearch())
    cell = json.loads((run_dir / "summary.json").read_text())["search"]["hybrid"]["10"]
    assert cell["searched"] == 3 and cell["search_errors"] == 3
