"""``python -m evals.run regrade <run_dir>``: re-grade a finished run offline with the current grader."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evals import routing_run as rr
from evals import run as run_mod
from evals.caseset import CaseSetError, sha256_file
from evals.schema import case_from_dict, save_case
from evals.run_store import RegradeError, read_jsonl, regrade

CASES_DIR = Path("evals/cases/v1")
EXP1 = Path("evals/results/20261107T095436Z-milestone-a-does-legacy-degrade-from-n-1")
NOW = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
EXP1_MANIFEST_SHA256 = "eb5f510b2a88a0eea0fadce016515fab81f582c0d360da9f00096134d88be8f7"


def cases_as_run_by_exp1(dest: Path) -> Path:
    """The v1 set as experiment 1 ran it: the live set with its later amendments undone."""
    shutil.copytree(CASES_DIR, dest)
    manifest = json.loads((dest / "MANIFEST.json").read_text())
    for a in reversed(manifest.pop("amendments", [])):
        if a["case"] == "trigger-006":  # 2026-11-07: "these" -> "this"
            f = dest / "trigger-006.json"
            c = json.loads(f.read_text())
            c["message"] = c["message"].replace("push this back", "push these back")
            c["original_message"] = c["original_message"].replace("make this come", "make these come")
            save_case(case_from_dict(c), f)
    for e in manifest["cases"]:
        e["sha256"] = sha256_file(dest / e["file"])
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    assert sha256_file(dest / "MANIFEST.json") == EXP1_MANIFEST_SHA256
    return dest


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    async def aboom(*args, **kwargs):
        raise AssertionError("regrade must not call an LLM")

    monkeypatch.setattr(rr, "default_llm", lambda: aboom)


@pytest.fixture
def exp1(tmp_path):
    """A copy of experiment 1's folder and of EXPERIMENTS.md (the real ones are never touched)."""
    root = tmp_path / "results"
    root.mkdir()
    # Leave out earlier regrade backups (*.v1.*): each test starts from the run as first written.
    shutil.copytree(EXP1, root / EXP1.name, ignore=shutil.ignore_patterns("*.v[0-9]*.*"))
    shutil.copy(EXP1.parent / "EXPERIMENTS.md", root / "EXPERIMENTS.md")
    cases_as_run_by_exp1(tmp_path / "cases_exp1")
    return root / EXP1.name


def old_cases(exp1: Path) -> Path:
    return exp1.parent.parent / "cases_exp1"


def test_regrade_experiment_1_fixes_the_reuse_false_negatives(exp1):
    records_before = (exp1 / "records.jsonl").read_text()
    summary = regrade(exp1, cases_dir=old_cases(exp1), now=NOW)
    assert (exp1 / "records.jsonl").read_text() == records_before  # records are never rewritten
    cell = summary["pass_rate"]["legacy"]
    assert (cell["10"]["passed"], cell["10"]["graded"]) == (9, 16)
    assert (cell["300"]["passed"], cell["300"]["graded"]) == (7, 16)
    grades = {(g["case_id"], g["n"]): g for g in read_jsonl(exp1 / "grades.jsonl")}
    for key in [("amb-person-007", 10), ("followup-005", 10), ("followup-006", 10), ("followup-006", 300)]:
        assert grades[key]["passed"] and grades[key]["person_ok"] is False, key
    assert not grades[("followup-005", 300)]["passed"]  # a duplicate create stays a failure
    failing = {(f["case_id"], f["n"]) for f in summary["failing"]}
    assert len(failing) == 16 and ("followup-006", 10) not in failing
    assert summary["regraded"][-1]["date_utc"] == "2026-11-08T10:00:00Z"
    assert summary["counts"]["graded"] == 32 and summary["cost"]["actual_usd"] == pytest.approx(0.06097)


def test_regrade_keeps_previous_versions_and_what_we_learned(exp1):
    learned_line = "Broad questions fail at every N (0/4)"
    assert learned_line in (exp1 / "report.md").read_text()
    regrade(exp1, cases_dir=old_cases(exp1), now=NOW)
    for name in ["grades.v{}.jsonl", "summary.v{}.json", "report.v{}.md"]:
        assert any((exp1 / name.format(k)).exists() for k in range(1, 4)), name
    report = (exp1 / "report.md").read_text()
    head, learned = report.split("## What we learned", 1)
    assert learned_line in learned
    assert learned.lstrip().startswith("*Regraded on 2026-11-08")
    assert "Before: legacy N=10 38% (6/16), N=300 38% (6/16)" in learned or "Before: legacy N=10 56%" in learned
    assert "After: legacy N=10 56% (9/16), N=300 44% (7/16)" in learned
    assert "**Regraded:** 2026-11-08" in head
    assert "| followup-006 |" not in head  # no longer a failing case-run


def test_regrade_twice_keeps_both_versions_and_the_learned_text_once(exp1):
    regrade(exp1, cases_dir=old_cases(exp1), now=NOW)
    first = sorted(p.name for p in exp1.glob("report.v*.md"))
    regrade(exp1, cases_dir=old_cases(exp1), now=NOW)
    second = sorted(p.name for p in exp1.glob("report.v*.md"))
    assert len(second) == len(first) + 1
    report = (exp1 / "report.md").read_text()
    assert report.count("Broad questions fail at every N (0/4)") == 1
    assert report.count("## What we learned") == 1


def test_regrade_updates_the_experiments_line(exp1):
    regrade(exp1, cases_dir=old_cases(exp1), now=NOW)
    lines = (exp1.parent / "EXPERIMENTS.md").read_text().splitlines()
    rows = [line for line in lines if EXP1.name in line]
    assert len(rows) == 1
    assert "legacy N=10 56% (9/16), N=300 44% (7/16)" in rows[0] and "regraded 2026-11-08" in rows[0]
    assert "$0.0610" in rows[0]
    assert lines[0] == "# Experiments"


def test_regrade_refuses_a_different_case_set(exp1, tmp_path):
    summary = json.loads((exp1 / "summary.json").read_text())
    summary["case_set"]["manifest_sha256"] = "0" * 64
    (exp1 / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(RegradeError, match="MANIFEST"):
        regrade(exp1, cases_dir=old_cases(exp1), now=NOW)
    assert not list(exp1.glob("*.v*.*"))  # nothing written


def test_regrade_refuses_a_different_world(exp1):
    summary = json.loads((exp1 / "summary.json").read_text())
    summary["case_set"]["world_sha256"] = "0" * 64
    (exp1 / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(RegradeError, match="world"):
        regrade(exp1, cases_dir=old_cases(exp1), now=NOW)


def test_regrade_refuses_a_tampered_case_set(exp1, tmp_path):
    d = old_cases(exp1)
    p = d / "followup-006.json"
    p.write_text(p.read_text().replace("Theo", "Thea"))
    with pytest.raises(CaseSetError, match="modified"):
        regrade(exp1, cases_dir=d, now=NOW)


def test_regrade_cli(exp1, capsys):
    rc = run_mod.main(["regrade", str(exp1), "--cases-dir", str(old_cases(exp1))])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "N=10 56% (9/16)" in out and "no LLM calls" in out
    rc = run_mod.main(["regrade", str(exp1.parent / "missing")])
    assert rc == 1


def test_regrade_of_a_fresh_run_is_stable(tmp_path):
    """A run written by the current runner regrades to the same grades and keeps its error tally."""
    from test_routing_run import RoutedFake, config, execute, jsonl

    run_dir, _ = execute(tmp_path, config(sizes=[10]), RoutedFake(fail={"Daniel gotten back"}))
    before = jsonl(run_dir / "grades.jsonl")
    summary = regrade(run_dir, now=NOW)
    assert jsonl(run_dir / "grades.jsonl") == before
    assert summary["error_kinds"] == {"OpenRouterError": 1}
    assert (run_dir / "report.md").read_text().count("## What we learned") == 1


def test_regrade_refuses_runs_made_before_a_case_amendment(exp1):
    """Experiments 1-4 ran trigger-006 with "these": the amended live set must not regrade them."""
    with pytest.raises(RegradeError, match="MANIFEST"):
        regrade(exp1, now=NOW)
