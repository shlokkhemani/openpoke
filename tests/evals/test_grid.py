"""``evals.grid``: case x N pass grid for one run and an experiment diff; reads grades.jsonl only."""
import shutil
from pathlib import Path

import pytest

from evals import run as run_mod
from evals.grid import diff, grid
from tests.evals.synthetic_run import write_run

EXP5 = Path("evals/results/20261107T234451Z-exp5-full-dev")


def rows(case, mode, n, passes, runs=3):
    return [(case, mode, n, i, i < passes, "dispatch" if i < passes else "none", [], None) for i in range(runs)]


A_ROWS = (rows("case-a", "legacy", 10, 3) + rows("case-a", "legacy", 30, 2) + rows("case-b", "legacy", 10, 1)
          + rows("case-a", "full", 10, 3))
B_ROWS = (rows("case-a", "legacy", 10, 3) + rows("case-a", "legacy", 30, 3) + rows("case-b", "legacy", 10, 1)
          + rows("case-c", "legacy", 10, 2))


@pytest.fixture
def run_a(tmp_path):
    return write_run(tmp_path / "a", A_ROWS, name="run-a")


@pytest.fixture
def run_b(tmp_path):
    return write_run(tmp_path / "b", B_ROWS, name="run-b")


def cells(line):
    return line.split()


def table(text, mode):
    """The block of ``text`` for one mode: from its heading line to the next mode's heading (or the end)."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().lstrip("#* ").startswith(mode))
    rest = lines[start + 1:]
    end = next((i for i, line in enumerate(rest) if line.strip().lstrip("#* ").split(" ")[0] in ("legacy", "full")),
               len(rest))
    return "\n".join(rest[:end])


def line_for(block, case):
    return next(line for line in block.splitlines() if line.lstrip().startswith(case))


def test_grid_has_one_table_per_mode_with_n_columns(run_a):
    text = grid(run_a)
    for mode in ("legacy", "full"):
        assert sum(1 for line in text.splitlines() if line.strip().lstrip("#* ").startswith(mode)) == 1
    header = next(line for line in table(text, "legacy").splitlines() if "10" in line.split() and "30" in line.split())
    assert header.split().index("10") < header.split().index("30")


def test_grid_cells_are_passes_over_runs_with_failures_marked(run_a):
    legacy = table(grid(run_a), "legacy")
    a = line_for(legacy, "case-a")
    assert "cat-a" in a
    assert cells(a)[-3:] == ["3/3", "2/3", "✗"]
    assert "✗" not in a.split("2/3")[0]
    b = line_for(legacy, "case-b")
    assert "1/3 ✗" in b and "3/3 ✗" not in b


def test_grid_missing_cell_is_a_dash(run_a):
    b = line_for(table(grid(run_a), "legacy"), "case-b")
    assert cells(b)[-1] == "-"


def test_diff_lists_only_changed_cells(run_a, run_b):
    text = diff(run_a, run_b)
    assert "case-a legacy 30: 2/3 → 3/3" in text
    assert "case-a legacy 10" not in text and "case-b legacy 10" not in text


def test_diff_lists_cells_present_in_only_one_run_separately(run_a, run_b):
    text = diff(run_a, run_b)
    only_a = [line for line in text.splitlines() if "only in" in line and "case-a full 10" in line]
    only_b = [line for line in text.splitlines() if "only in" in line and "case-c legacy 10" in line]
    assert len(only_a) == 1 and "3/3" in only_a[0]
    assert len(only_b) == 1 and "2/3" in only_b[0]
    assert "case-a full 10: " not in text.replace(only_a[0], "")


def test_diff_of_identical_runs_reports_no_changes(run_a):
    text = diff(run_a, run_a)
    assert "→" not in text and "only in" not in text


@pytest.fixture
def exp5_pair(tmp_path):
    v1, now = tmp_path / "v1" / "exp5-v1", tmp_path / "now" / "exp5-regraded"
    for dest in (v1, now):
        shutil.copytree(EXP5, dest, ignore=shutil.ignore_patterns("*.v[0-9]*.*"))
    shutil.copy(EXP5 / "grades.v1.jsonl", v1 / "grades.jsonl")
    return v1, now


def test_diff_experiment_5_v1_against_regraded_shows_amb_person_006(exp5_pair):
    v1, now = exp5_pair
    text = diff(v1, now)
    assert "amb-person-006 full 10: 0/3 → 3/3" in text
    assert "only in" not in text


def test_grid_on_real_run_marks_a_failing_cell(exp5_pair):
    _, now = exp5_pair
    assert "✗" in grid(now) and "full" in grid(now)


def test_cli_grid_prints_the_table(run_a, capsys):
    assert run_mod.main(["grid", str(run_a)]) == 0
    out = capsys.readouterr().out
    assert "case-a" in out and "2/3 ✗" in out


def test_cli_grid_with_diff_prints_the_diff_instead(run_a, run_b, capsys):
    assert run_mod.main(["grid", str(run_b), "--diff", str(run_a)]) == 0
    out = capsys.readouterr().out
    assert "case-a legacy 30: 2/3 → 3/3" in out
    assert "case-b" not in out


def test_cli_grid_diff_goes_from_the_baseline_to_the_run(exp5_pair, capsys):
    v1, now = exp5_pair
    assert run_mod.main(["grid", str(now), "--diff", str(v1)]) == 0
    assert "amb-person-006 full 10: 0/3 → 3/3" in capsys.readouterr().out
