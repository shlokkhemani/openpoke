"""Task 13-R: the ``recency`` roster mode and the eval reuse mechanism (which existed only for it) are gone."""
import dataclasses
import json
from pathlib import Path

import pytest

from evals import routing_run as rr
from evals.grading import EVAL_MODES, NAME_DISPATCH_MODES, ROSTER_MODES, classify
from evals.inspect_export import export_run
from tests.evals.synthetic_run import write_run
from tests.evals.test_routing_run import config, execute, jsonl


def test_recency_is_not_a_mode():
    assert "recency" not in ROSTER_MODES and "recency" not in EVAL_MODES
    assert "recency" not in NAME_DISPATCH_MODES
    assert ROSTER_MODES == ("legacy", "full", "hybrid")
    assert NAME_DISPATCH_MODES == frozenset({"legacy", "legacy_rules"})
    assert "recency" not in rr.PROMPT_TOKENS_PER_CASE_RUN
    assert "recency" not in rr._ROUGH_PER_TURN
    assert not hasattr(rr, "REUSE_SOURCE") and not hasattr(rr, "RECENCY_CUTOFF")
    with pytest.raises(ValueError, match="unknown roster mode"):
        classify([], [], "recency")


def test_reuse_fields_are_gone_from_the_runner_types():
    assert not hasattr(rr.CaseRun, "reuse_source")
    assert "reused" not in {f.name for f in dataclasses.fields(rr.Estimate)}
    assert "reused_from" not in {f.name for f in dataclasses.fields(rr.CaseRunResult)}


def test_estimate_has_no_reused_count():
    cfg = config(case_ids=["clear-person-005"], sizes=[10])
    est = rr.estimate(cfg, rr.load_run_cases(cfg, Path("evals/cases/v1")))
    assert not hasattr(est, "reused")


def test_summary_and_rows_have_no_reuse_or_recency_keys(tmp_path):
    run_dir, _ = execute(tmp_path, config(case_ids=["clear-person-005"], sizes=[10]))
    summary = json.loads((run_dir / "summary.json").read_text())
    assert not [k for k in summary["counts"] if k.startswith("reused")]
    assert "recency_cutoff" not in json.dumps(summary) and "reused" not in json.dumps(summary)
    for row in jsonl(run_dir / "records.jsonl"):
        assert "reused_from" not in row
    assert "reused" not in (run_dir / "report.md").read_text().lower()


def test_old_rows_with_reused_from_still_export_from_the_source_transcript(tmp_path):
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import read_eval_log

    # An old copied row: its own mode's transcript does not exist, only the source mode's ("legacy").
    run = write_run(tmp_path / "runs", [("case-a", "legacy_rules", 10, 0, True, "dispatch", [], "legacy")])
    [p] = export_run(run, tmp_path / "logs")
    assert p.name == "legacy_rules-N10.eval"
    [s] = read_eval_log(str(p)).samples
    assert s.metadata["mode"] == "legacy_rules"
    assert "please do case-a-legacy" in json.dumps([m.content for m in s.messages])
    assert not s.metadata.get("transcript_missing")


def test_regrade_reads_an_old_rows_reused_from_as_its_graded_mode(tmp_path):
    import shutil

    from evals.run_store import read_jsonl, regrade
    from tests.evals.test_regrade import EXP1, NOW, cases_as_run_by_exp1

    root = tmp_path / "results"
    root.mkdir()
    run = root / EXP1.name
    shutil.copytree(EXP1, run, ignore=shutil.ignore_patterns("*.v[0-9]*.*"))
    shutil.copy(EXP1.parent / "EXPERIMENTS.md", root / "EXPERIMENTS.md")
    cases = cases_as_run_by_exp1(tmp_path / "cases_exp1")
    rows = read_jsonl(run / "records.jsonl")
    key = (rows[0]["case_id"], rows[0]["n"], rows[0]["run_idx"])
    rows[0]["reused_from"] = "legacy_rules"  # an old row graded as another mode
    (run / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    regrade(run, cases_dir=cases, now=NOW)
    graded_as = {(g["case_id"], g["n"], g["run_idx"]): g["graded_as"] for g in read_jsonl(run / "grades.jsonl")}
    assert graded_as[key] == "legacy_rules"
    assert {v for k, v in graded_as.items() if k != key} == {"legacy"}
