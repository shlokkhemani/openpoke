"""Run folders: written as a routing run goes, read back, and regraded offline.

A run folder holds ``records.jsonl`` (graded records), ``grades.jsonl``, ``errors.jsonl``,
``transcripts/``, ``summary.json`` and ``report.md``. ``RunWriter`` appends each case-run's files
the moment it completes, so a crash never loses paid results; at the end of a normal run the
jsonl files are rewritten in plan order. ``grade_tables`` builds the graded part of
``summary.json`` for both the runner and ``regrade``.

``regrade(run_dir)`` re-grades a finished run's ``records.jsonl`` with the current grader and the
same rosters (``roster_for(case, world, n)``), without any LLM call. It first checks that the
frozen case set and the world are the ones the run used: ``load_frozen_cases`` checks the world
against the MANIFEST, and the MANIFEST sha must equal the run's (summaries written since
2026-11-07 also record ``world_sha256``, checked directly). The previous ``grades.jsonl``,
``summary.json`` and ``report.md`` are kept as ``*.v<k>.*`` (k = 1, 2, ...), the hand-written
"What we learned" section is carried over under a dated "Regraded" note, and the run's line in
``EXPERIMENTS.md`` is replaced and marked "regraded". Nothing is written if any record fails to
grade.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from evals.caseset import load_frozen_cases, sha256_file
from evals.caseset import CASES_DIR
from evals.grading import Grade, RunRecord, ToolCall, grade
from evals.report_run import WHAT_WE_LEARNED, headline, render_report, update_experiment
from evals.schema import Case, format_outcome
from evals.world.generate import WORLD_PATH
from evals.world.roster import load_world, roster_for

_REPO_ROOT = Path(__file__).resolve().parent.parent
SECRET_KEYS = {"api_key", "authorization", "headers", "x-api-key"}
RUNNER_ERROR = "RunnerError"


# ---------------------------------------------------------------- writing

def scrub(obj: Any, secrets: list[str]) -> Any:
    """Drop secret-bearing keys and redact secret values, recursively."""
    if isinstance(obj, dict):
        return {k: scrub(v, secrets) for k, v in obj.items() if str(k).lower() not in SECRET_KEYS}
    if isinstance(obj, (list, tuple)):
        return [scrub(v, secrets) for v in obj]
    if isinstance(obj, set):
        return sorted(scrub(v, secrets) for v in obj)
    if isinstance(obj, str):
        for s in secrets:
            obj = obj.replace(s, "[REDACTED]")
    return obj


def _line(row: dict[str, Any], secrets: list[str]) -> str:
    return json.dumps(scrub(row, secrets), ensure_ascii=False) + "\n"


def write_jsonl(path: Path, rows: list[dict[str, Any]], secrets: list[str]) -> None:
    Path(path).write_text("".join(_line(r, secrets) for r in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class RunWriter:
    """Writes one run folder, scrubbing every object of ``secrets``."""

    def __init__(self, run_dir: Path, secrets: list[str]) -> None:
        self.run_dir, self.secrets = Path(run_dir), secrets
        (self.run_dir / "transcripts").mkdir(parents=True)
        for name in ("records", "grades", "errors"):
            (self.run_dir / f"{name}.jsonl").touch()

    def append(self, name: str, row: dict[str, Any]) -> None:
        with (self.run_dir / f"{name}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(_line(row, self.secrets))

    def rewrite(self, name: str, rows: list[dict[str, Any]]) -> None:
        write_jsonl(self.run_dir / f"{name}.jsonl", rows, self.secrets)

    def transcript(self, filename: str, doc: dict[str, Any]) -> None:
        (self.run_dir / "transcripts" / filename).write_text(
            json.dumps(scrub(doc, self.secrets), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    def text(self, filename: str, text: str) -> None:
        (self.run_dir / filename).write_text(scrub(text, self.secrets), encoding="utf-8")


# ---------------------------------------------------------------- grade rows and tables

def grade_row(case: Case, record: RunRecord, g: Grade, graded_as: str) -> dict[str, Any]:
    row = {"case_id": case.id, "mode": record.mode, "n": record.n, "run_idx": record.run_idx,
           "category": case.category, "graded_as": graded_as}
    row.update(asdict(g))
    row["flags"] = sorted(g.flags)
    return row


def record_from_row(row: dict[str, Any]) -> RunRecord:
    fields = RunRecord.__dataclass_fields__
    optional = {"searches", "initial_ids"}  # absent in records written before hybrid
    kw = {k: row[k] for k in fields if k != "calls" and not (k in optional and k not in row)}
    return RunRecord(calls=[ToolCall(c["name"], c["args"]) for c in row["calls"]], **kw)


def failure_reason(case: Case, record: RunRecord, g: Grade) -> str:
    """One line: what was acceptable, what the IA did, and why it failed."""
    want = " | ".join(format_outcome(o) for o in case.acceptable)
    did = []
    for c in record.calls:
        if c.name == "send_message_to_agent":
            target = c.args.get("agent_id") or c.args.get("agent_name") or c.args.get("name") or "?"
            did.append(f"dispatch→{target!s}")
        elif c.name == "send_message_to_user":
            did.append("message_user")
        else:
            did.append(c.name)
    parts = [f"expected {want}; got {g.outcome_kind}" + (f" ({', '.join(did)})" if did else " (no tool calls)")]
    if g.structural:
        parts.append("structural: a dispatched name matches several agents")
    # person_ok is informational on a reuse (grading docstring): cite it only where it decides.
    if g.person_ok is False and any(o.kind == "create" for o in case.acceptable):
        parts.append("wrong person in instructions")
    if g.slots_total:
        parts.append(f"slots {g.slots_filled}/{g.slots_total}")
    text = "; ".join(parts)
    return text if len(text) <= 220 else text[:217] + "..."


def cells(modes: list[str], sizes: list[int], value: Callable[[], Any]) -> dict[str, dict[str, Any]]:
    return {m: {str(n): value() for n in sizes} for m in modes}


def grade_tables(modes: list[str], sizes: list[int], cases: list[Case],
                 graded: list[tuple[Case, RunRecord, Grade]]) -> dict[str, Any]:
    """``pass_rate``, ``by_category``, ``flags``, ``structural`` and ``failing`` of a summary."""
    rate = lambda: {"passed": 0, "graded": 0, "rate": None}  # noqa: E731
    pass_rate = cells(modes, sizes, rate)
    by_category = {cat: cells(modes, sizes, rate) for cat in sorted({c.category for c in cases})}
    flags = cells(modes, sizes, dict)
    structural = cells(modes, sizes, int)
    failing = []
    for case, rec, g in graded:
        key = str(rec.n)
        for cell in (pass_rate[rec.mode][key], by_category[case.category][rec.mode][key]):
            cell["graded"] += 1
            cell["passed"] += int(g.passed)
        for f in g.flags:
            flags[rec.mode][key][f] = flags[rec.mode][key].get(f, 0) + 1
        structural[rec.mode][key] += int(g.structural)
        if not g.passed:
            failing.append({"case_id": case.id, "category": case.category, "mode": rec.mode, "n": rec.n,
                            "run_idx": rec.run_idx, "outcome_kind": g.outcome_kind, "flags": sorted(g.flags),
                            "structural": g.structural, "reason": failure_reason(case, rec, g)})
    for table in [pass_rate, *by_category.values()]:
        for row in table.values():
            for cell in row.values():
                cell["rate"] = cell["passed"] / cell["graded"] if cell["graded"] else None
    return {"pass_rate": pass_rate, "by_category": by_category, "flags": flags, "structural": structural,
            "failing": failing}


# ---------------------------------------------------------------- error kinds

def error_kind(error: str) -> str:
    """The tally bucket of an infra error string (its ``Prefix:``; the iteration limit and timeouts by name)."""
    if "iteration limit" in error.lower():
        return "IterationLimit"
    prefix = error.split(":", 1)[0].strip() if ":" in error else ""
    if prefix in ("TimeoutError", "asyncio.TimeoutError"):
        return "Timeout"
    return prefix if prefix.isidentifier() else "Other"


def error_tables(errors: list[dict[str, Any]]) -> tuple[dict[str, int], list[str]]:
    """(count per error kind, the iteration-limit case-runs) over error rows (one per paid case-run)."""
    kinds: dict[str, int] = {}
    loops = []
    for e in errors:
        kind = error_kind(e.get("error") or "")
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "IterationLimit":
            loops.append(f"{e['case_id']} {e['mode']} N={e['n']} run {e['run_idx']}")
    return dict(sorted(kinds.items())), loops


# ---------------------------------------------------------------- regrade

class RegradeError(Exception):
    """The run cannot be regraded with the current case set and world."""


def _next_version(run_dir: Path) -> int:
    k = 1
    while any((run_dir / f"{stem}.v{k}.{ext}").exists()
              for stem, ext in (("grades", "jsonl"), ("summary", "json"), ("report", "md"))):
        k += 1
    return k


def _learned(report: str) -> str:
    """The body of the report's "What we learned" section ("" if absent)."""
    head = f"\n{WHAT_WE_LEARNED}\n"
    i = report.find(head)
    return report[i + len(head):].strip("\n") if i >= 0 else ""


def regrade(run_dir: Path, *, cases_dir: Optional[Path] = None, world_path: Path = WORLD_PATH,
            now: Optional[datetime] = None) -> dict[str, Any]:
    """Re-grade ``run_dir`` in place (see the module docstring). Returns the new summary."""
    run_dir = Path(run_dir)
    now = now or datetime.now(timezone.utc)
    old = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    if cases_dir is None:
        recorded = old.get("case_set", {}).get("dir")
        cases_dir = (_REPO_ROOT / recorded) if recorded else CASES_DIR  # absolute paths win over the root
    cases = {c.id: c for c in load_frozen_cases(Path(cases_dir), Path(world_path))}  # raises CaseSetError
    manifest_sha = sha256_file(Path(cases_dir) / "MANIFEST.json")
    run_set = old.get("case_set", {})
    if run_set.get("manifest_sha256") != manifest_sha:
        raise RegradeError(f"case set MANIFEST sha256 {manifest_sha} differs from the run's "
                           f"{run_set.get('manifest_sha256')}")
    if "world_sha256" in run_set and run_set["world_sha256"] != sha256_file(Path(world_path)):
        raise RegradeError(f"world sha256 differs from the run's ({world_path})")
    missing = [i for i in old["case_ids"] if i not in cases]
    if missing:
        raise RegradeError(f"run cases not in the case set: {', '.join(missing)}")
    world = load_world(Path(world_path))

    rows = read_jsonl(run_dir / "records.jsonl")
    graded, grade_rows = [], []
    for row in rows:
        rec, case = record_from_row(row), cases[row["case_id"]]
        graded_as = row.get("reused_from") or rec.mode
        g = grade(case, rec, roster_for(case, world, rec.n), graded_as)
        graded.append((case, rec, g))
        grade_rows.append(grade_row(case, rec, g, graded_as))

    run_cases = [cases[i] for i in old["case_ids"]]
    summary = dict(old)
    summary.update(grade_tables(old["modes"], old["sizes"], run_cases, graded))
    kinds, loops = error_tables(read_jsonl(run_dir / "errors.jsonl"))
    summary.setdefault("error_kinds", kinds)
    summary.setdefault("iteration_limit", loops)
    date = now.strftime("%Y-%m-%d")
    entry = {"date_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "previous_headline": headline(old),
             "headline": headline(summary), "graded": len(graded)}
    summary["regraded"] = [*old.get("regraded", []), entry]

    version = _next_version(run_dir)
    old_report = (run_dir / "report.md").read_text(encoding="utf-8") if (run_dir / "report.md").exists() else ""
    note = (f"*Regraded on {date} with the current grader (`python -m evals.run regrade`; see "
            f"`evals/results/changes.md`); previous files kept as `*.v{version}.*`. "
            f"Before: {entry['previous_headline']}. After: {entry['headline']}. "
            f"Notes below this line were written against the earlier grading.*")
    learned = _learned(old_report)
    report = render_report(summary) + "\n" + note + "\n" + (f"\n{learned}\n" if learned else "")

    for stem, ext in (("grades", "jsonl"), ("summary", "json"), ("report", "md")):
        src = run_dir / f"{stem}.{ext}"
        if src.exists():
            src.rename(run_dir / f"{stem}.v{version}.{ext}")
    write_jsonl(run_dir / "grades.jsonl", grade_rows, [])
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    update_experiment(run_dir.parent / "EXPERIMENTS.md", summary, f"regraded {date}; was: {entry['previous_headline']}")
    return summary
