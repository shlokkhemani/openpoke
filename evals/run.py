"""Run the original-vs-fork evaluation.

Usage (from the fork repo root, with the OpenPoke virtualenv's python):

    ~/Repositories/openpoke/.venv/bin/python -m evals.run \
        --original ~/Repositories/openpoke --fork . \
        --env-file ~/Repositories/openpoke/.env \
        --python ~/Repositories/openpoke/.venv/bin/python \
        --judge-model <openrouter-model-id> --repeats 3 --workers 4

    python -m evals.run --dry-run                       # validate scenarios, no server, no LLM calls
    python -m evals.run --report-only runs/<timestamp>   # rebuild the report from existing runs
    python -m evals.run --rescore runs/<timestamp>       # re-apply current checks to recorded runs (add --judge-model to re-judge too)
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .evaluators.checks import RunData, always_on_checks, run_check, validate_spec
from .evaluators.judge import judge_run, read_api_key
from .evaluators.metrics import compute_metrics
from .harness.runner import RunOptions, run_scenario
from .harness.timeexpr import resolve
from .report import build_report

SCENARIO_DIR = Path(__file__).with_name("scenarios")


def load_cases(selector: str) -> List[Dict[str, Any]]:
    cases = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(SCENARIO_DIR.glob("*.yaml"))]
    if selector in ("", "all"):
        return cases
    wanted = {s.strip() for s in selector.split(",") if s.strip()}
    return [c for c in cases if c["id"] in wanted or c["id"].split("-")[0] in wanted or c.get("group") in wanted]


def dry_run(cases: List[Dict[str, Any]], tz: str) -> int:
    errors = 0
    now = datetime.now(timezone.utc)

    def walk(spec: Dict[str, Any]):
        yield spec
        for sub in spec.get("checks", []):
            yield from walk(sub)

    for case in cases:
        problems: List[str] = []
        if not case.get("turns"):
            problems.append("no turns")
        n_steps = len(case.get("turns", []))
        case_tz = (case.get("config") or {}).get("timezone", tz)
        for spec in case.get("checks", []):
            problems.extend(validate_spec(spec))
            for sub in walk(spec):
                if "expect" in sub and isinstance(sub["expect"], str):
                    try:
                        resolve(sub["expect"], now, case_tz)
                    except ValueError as exc:
                        problems.append(str(exc))
                for key in ("after_step", "from_step"):
                    if isinstance(sub.get(key), int) and not 1 <= sub[key] <= n_steps:
                        problems.append(f"{key}={sub[key]} out of range (1..{n_steps})")
        status = "OK " if not problems else "ERR"
        errors += bool(problems)
        print(f"{status} {case['id']:<24} steps={n_steps:<3} checks={len(case.get('checks', []))}"
              + (f"  -> {problems}" if problems else ""))
    print(f"\n{len(cases)} cases, {errors} with errors")
    return 1 if errors else 0


def rescore(out: Path, judge_model: str | None = None, api_key: str | None = None) -> int:
    """Recompute checks and metrics for recorded runs. Judge scores are kept, or re-done when a judge model is given."""
    cases = {c["id"]: c for c in load_cases("all")}
    count = 0
    for path in sorted(out.glob("*/*/run_*/result.json")):
        old = json.loads(path.read_text(encoding="utf-8"))
        case = cases.get(old["case"])
        if case is None:
            continue
        new = score_run(path.parent, case, judge_model, api_key)
        if not judge_model:
            new["judge"] = old.get("judge")
        path.write_text(json.dumps(new, indent=2, default=str))
        count += 1
    return count


def score_run(folder: Path, case: Dict[str, Any], judge_model: str | None, api_key: str | None) -> Dict[str, Any]:
    run = RunData.load(folder)
    checks = [run_check(run, spec) for spec in case.get("checks", [])]
    always = always_on_checks(run)
    result: Dict[str, Any] = {
        "case": case["id"], "group": case.get("group"), "version": run.meta.get("version"),
        "checks": [asdict(c) for c in checks], "always_on": [asdict(c) for c in always],
        "passed": all(c.passed for c in checks + always),
        "metrics": compute_metrics(run),
        "case_metrics": {c.metric: c.value for c in checks if c.metric},
        "judge": None,
    }
    if judge_model and api_key:
        result["judge"] = judge_run(run, case.get("judge", ""), model=judge_model, api_key=api_key)
    (folder / "result.json").write_text(json.dumps(result, indent=2, default=str))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--original", type=Path, default=Path("~/Repositories/openpoke").expanduser())
    parser.add_argument("--fork", type=Path, default=Path("."))
    parser.add_argument("--env-file", type=Path, default=Path("~/Repositories/openpoke/.env").expanduser())
    parser.add_argument("--python", default=str(Path("~/Repositories/openpoke/.venv/bin/python").expanduser()))
    parser.add_argument("--cases", default="all", help="'all', group letters (A,B,C,R), or case ids, comma separated")
    parser.add_argument("--versions", default="original,fork")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4, help="Scenario runs to execute in parallel")
    parser.add_argument("--judge-model", default=None, help="OpenRouter model id for the judge (omit to skip judging)")
    parser.add_argument("--model", default=None, help="Pin every agent model in both versions to this id")
    parser.add_argument("--timezone", default="America/Los_Angeles")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-only", type=Path, default=None)
    parser.add_argument("--rescore", type=Path, default=None, help="Recompute checks/metrics of a runs folder, keep judge scores")
    parser.add_argument("--keep-tmp", action="store_true", help="Keep the temp server copies for debugging")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    if args.dry_run:
        return dry_run(cases, args.timezone)
    if args.rescore:
        key = read_api_key(str(args.env_file)) if args.judge_model else None
        print(f"rescored {rescore(args.rescore, args.judge_model, key)} runs")
        print(build_report(args.rescore))
        return 0
    if args.report_only:
        print(build_report(args.report_only))
        return 0

    if not args.env_file.exists():
        print(f"env file not found: {args.env_file}", file=sys.stderr)
        return 2
    api_key = read_api_key(str(args.env_file))
    if args.judge_model and not api_key:
        print("judge needs OPENROUTER_API_KEY (env var or in --env-file)", file=sys.stderr)
        return 2

    checkouts = {"original": args.original.expanduser().resolve(), "fork": args.fork.expanduser().resolve()}
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    for version in versions:
        if not (checkouts[version] / "server" / "app.py").exists():
            print(f"{version}: no server/app.py under {checkouts[version]}", file=sys.stderr)
            return 2

    out = args.out or Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps({**vars(args), "checkouts": checkouts,
                                                 "cases": [c["id"] for c in cases]}, indent=2, default=str))
    opts = RunOptions(python=args.python, env_file=args.env_file.expanduser(), timezone=args.timezone,
                      model=args.model, keep_tmp=args.keep_tmp)

    # Job list in alternating original/fork order, so API latency drift hits both versions equally.
    # With --workers > 1, neighbouring jobs (usually the same case on both versions) run side by side.
    jobs = []
    for rep in range(1, args.repeats + 1):
        for case in cases:
            order = versions if (rep + cases.index(case)) % 2 == 0 else list(reversed(versions))
            for version in order:
                folder = out / version / case["id"] / f"run_{rep}"
                if not (folder / "result.json").exists():  # resume
                    jobs.append((case, version, rep, folder))

    total = len(jobs)
    counter = {"done": 0}
    print_lock = threading.Lock()

    def run_job(job) -> None:
        case, version, rep, folder = job
        started = time.time()
        try:
            run_scenario(case, version, checkouts[version], folder, opts)
            result = score_run(folder, case, args.judge_model, api_key)
            judge = result.get("judge") or {}
            status = f"{'PASS' if result['passed'] else 'FAIL'} judge={judge.get('score')}"
        except Exception as exc:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "error.txt").write_text(traceback.format_exc())
            status = f"ERROR {exc}"
        with print_lock:
            counter["done"] += 1
            print(f"[{counter['done']}/{total}] {version:<8} {case['id']:<24} run {rep}: {status} "
                  f"({time.time() - started:.0f}s)", flush=True)

    print(f"{total} scenario runs to do, {args.workers} at a time")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        list(pool.map(run_job, jobs))

    report = build_report(out)
    print(f"\nReport written to {out / 'report.md'}\n")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
