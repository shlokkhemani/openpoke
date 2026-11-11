"""Eval command line: ``build-cases``, ``freeze-cases``, ``routing`` and ``regrade``.

    python -m evals.run build-cases [--paraphrase] [--yes] [--out DIR]
    python -m evals.run build-cases-v2 [--force-unfreeze]   # v1 -> v2 (agent-backed history), no API calls
    python -m evals.run routing --modes legacy --sizes 10,300 --split dev --runs 1 [--yes] ...
    python -m evals.run regrade evals/results/<run folder>

Writes ``evals/cases/v1/<case_id>.json`` for every case and a ``MANIFEST.json`` (case ids, split,
sha256 of each file, generator seed, world sha256, paraphrase stats). ``freeze-cases`` verifies the set and marks the manifest frozen. Without ``--paraphrase`` no
API key is needed. With it, the estimated cost is printed first and nothing runs without ``--yes``.
``routing`` runs frozen cases through the real IA loop (``evals.routing_run``); it also prints its
estimate and refuses without ``--yes``. ``regrade`` re-grades a finished run with the current grader,
offline (``evals.run_store.regrade``).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from evals.caseset import CASES_DIR, V1_DIR, V2_DIR, CaseSetError, freeze_case_set, is_frozen, load_frozen_cases, read_manifest, sha256_file as _sha256
from evals.expand import expand
from evals.paraphrase import SYSTEM, LLM, ParaphraseReport, paraphrase
from evals.pricing import estimate_cost
from evals.product_history import productize
from evals.schema import Case, case_to_dict, load_cases, save_case, validate_cases
from evals.world.generate import EXAMPLES, SEED, WORLD_PATH
from evals.world.roster import load_world

EST_PROMPT_TOKENS = 260   # system prompt + per-case instructions + message, per attempt
EST_COMPLETION_TOKENS = 40
RETRY_MARGIN = 1.25       # allowance for the one retry on a failed check


def estimate_paraphrase(cases: list[Case], model: str) -> tuple[int, int, int, float]:
    """(template cases, est. prompt tokens, est. completion tokens, est. USD)."""
    n = sum(c.source == "template" for c in cases)
    prompt, completion = int(n * EST_PROMPT_TOKENS * RETRY_MARGIN), int(n * EST_COMPLETION_TOKENS * RETRY_MARGIN)
    return n, prompt, completion, estimate_cost(model, prompt, completion)


def build_cases(out_dir: Path = V1_DIR, *, paraphrase_cases: bool = False, llm: Optional[LLM] = None,
                model: Optional[str] = None, force_unfreeze: bool = False) -> ParaphraseReport | None:
    """Generate the case set into ``out_dir`` (stale files removed first). Returns the paraphrase report.

    Raises CaseSetError if ``out_dir`` holds a frozen set and ``force_unfreeze`` is not set."""
    out_dir = Path(out_dir)
    if is_frozen(out_dir) and not force_unfreeze:
        raise CaseSetError(f"{out_dir} is frozen; refusing to overwrite it (pass --force-unfreeze to regenerate)")
    out_dir.mkdir(parents=True, exist_ok=True)
    world = load_world(WORLD_PATH)
    cases = expand(world, load_cases(EXAMPLES), seed=SEED)

    report: ParaphraseReport | None = None
    if paraphrase_cases:
        if model is None:
            from server.config import get_settings
            model = get_settings().eval_dev_model
        if llm is None:
            from functools import partial

            from server.config import get_settings
            from server.openrouter_client import request_chat_completion
            llm = partial(request_chat_completion, api_key=get_settings().openrouter_api_key)
        report = ParaphraseReport()
        cases = asyncio.run(paraphrase(cases, model, llm, world=world, report=report))

    for p in [*out_dir.glob("*.json"), out_dir / "paraphrase_errors.jsonl"]:
        p.unlink(missing_ok=True)
    entries = []
    for c in sorted(cases, key=lambda c: c.id):
        path = out_dir / f"{c.id}.json"
        save_case(c, path)
        entries.append({"id": c.id, "category": c.category, "split": c.split, "source": c.source,
                        "file": path.name, "sha256": _sha256(path)})
    stats = None
    if report is not None:
        stats = {"model": model, "kept": report.kept, "retried": report.retried, "reverted": report.reverted,
                 "infra_errors": len(report.errors), "prompt_tokens": report.prompt_tokens,
                 "completion_tokens": report.completion_tokens,
                 "cost_usd": round(report.cost(model), 6)}
        print(f"Paraphrase: kept {report.kept}, retried {report.retried}, reverted {report.reverted} "
              f"(infra errors: {len(report.errors)}); tokens {report.prompt_tokens} in / "
              f"{report.completion_tokens} out; actual cost ${stats['cost_usd']:.4f}")
        if report.errors:
            (out_dir / "paraphrase_errors.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in report.errors), encoding="utf-8")
    manifest = {"version": "v1", "generator": "evals.expand", "seed": SEED,
                "world_sha256": _sha256(WORLD_PATH), "n_cases": len(entries), "cases": entries,
                "paraphrase": stats}
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return report


def build_cases_v2(src: Path = V1_DIR, out_dir: Path = V2_DIR, world_path: Path = WORLD_PATH, *,
                   force_unfreeze: bool = False) -> None:
    """Derive the v2 case set (agent-backed history) from the frozen v1 set. No API calls."""
    src, out_dir = Path(src), Path(out_dir)
    cases = load_frozen_cases(src, world_path)
    if is_frozen(out_dir) and not force_unfreeze:
        raise CaseSetError(f"{out_dir} is frozen; refusing to overwrite it (pass --force-unfreeze to regenerate)")
    world = load_world(world_path)
    v2 = [productize(c, world, c.id) for c in cases]
    problems = validate_cases(v2)
    if problems:
        raise CaseSetError("v2 cases invalid:\n" + "\n".join(problems))
    src_manifest = read_manifest(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("*.json"):
        p.unlink()
    entries, changed = [], []
    for old, c in zip(cases, v2):
        if c.ia_history != old.ia_history:
            changed.append(c.id)
    for c in sorted(v2, key=lambda c: c.id):
        path = out_dir / f"{c.id}.json"
        save_case(c, path)
        entries.append({"id": c.id, "category": c.category, "split": c.split, "source": c.source,
                        "file": path.name, "sha256": _sha256(path)})
    manifest = {"version": "v2", "generator": "evals.product_history",
                "derived_from": {"dir": "evals/cases/v1", "manifest_sha256": _sha256(src / "MANIFEST.json")},
                "world_sha256": _sha256(world_path), "n_cases": len(entries), "cases": entries,
                "paraphrase": src_manifest.get("paraphrase"), "amendments": src_manifest.get("amendments"),
                "changed": sorted(changed)}
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    n_ctx = sum(len(c.context_agents) for c in v2)
    print(f"Wrote {out_dir}: {len(entries)} cases, {len(changed)} changed, {n_ctx} context agents. "
          f"Review, then: python -m evals.run freeze-cases --dir {out_dir}")


def _csv(text: str) -> list[str]:
    return [x.strip() for x in text.split(",") if x.strip()]


def _routing(args: argparse.Namespace, command: str) -> int:
    from evals import routing_run as rr

    try:
        sizes = [int(x) for x in _csv(args.sizes)]
    except ValueError:
        print(f"--sizes must be comma-separated integers, got {args.sizes!r}")
        return 1
    if not sizes or min(sizes) < 1 or args.runs < 1:
        print("--sizes needs at least one positive size and --runs must be >= 1")
        return 1
    config = rr.RoutingConfig(
        modes=_csv(args.modes), sizes=sizes, split=args.split, runs=args.runs,
        model=args.model or rr.default_model(), case_ids=_csv(args.cases) if args.cases else None,
        max_cost=rr.DEFAULT_MAX_COST if args.max_cost is None else args.max_cost,
        purpose=args.purpose,
        concurrency=rr.DEFAULT_CONCURRENCY if args.concurrency is None else args.concurrency,
        command=command, descriptions=args.descriptions, embedder=args.embedder)
    try:
        rr.check_modes(config.modes, rr.MODE_RUNNERS)
        descriptions = rr.resolve_descriptions(config)
        cases = rr.load_run_cases(config, args.cases_dir)
        est = rr.estimate(config, cases)
    except (CaseSetError, ValueError) as e:
        print(e)
        return 1
    print(f"Estimated cost: ${est.usd:.4f} for {est.case_runs} case-runs with {config.model} "
          f"({len(cases)} {config.split} cases × modes {','.join(config.modes)} × sizes "
          f"{','.join(map(str, sizes))} × {config.runs} run(s); "
          f"~{est.prompt_tokens:,} prompt + ~{est.completion_tokens:,} completion tokens). "
          f"Infra-error retries are extra; actual spend is capped at --max-cost ${config.max_cost:g} "
          f"(each case-run in flight reserves {rr.RESERVATION_MARGIN:g}x its estimate).")
    if not args.yes:
        print("Refusing to run without --yes.")
        return 2
    api_key = rr.configured_api_key()
    if not api_key:
        print("OPENROUTER_API_KEY is not set.")
        return 1
    from evals.world.roster import load_world

    run_dir = asyncio.run(rr.execute_routing(
        config, cases, load_world(WORLD_PATH), rr.default_llm(), args.out_root or rr.RESULTS_DIR,
        api_key=api_key, cases_dir=args.cases_dir, descriptions=descriptions))
    summary = json.loads((run_dir / "summary.json").read_text())
    from evals.report_run import headline

    c = summary["counts"]
    print(f"Wrote {run_dir}: {headline(summary)}; actual cost ${summary['cost']['actual_usd']:.4f}; "
          f"{c['graded']} graded, {c['infra_errors']} infra errors, {c['skipped_max_cost']} skipped by max-cost")
    return 0


def _regrade(args: argparse.Namespace) -> int:
    from evals.run_store import RegradeError, regrade

    run_dir = Path(args.run_dir)
    if not (run_dir / "summary.json").exists() or not (run_dir / "records.jsonl").exists():
        print(f"{run_dir}: not a run folder (needs summary.json and records.jsonl)")
        return 1
    try:
        summary = regrade(run_dir, cases_dir=args.cases_dir)
    except (CaseSetError, RegradeError) as e:
        print(e)
        return 1
    last = summary["regraded"][-1]
    print(f"Regraded {run_dir} ({last['graded']} records, no LLM calls): {last['previous_headline']} -> "
          f"{last['headline']}. Previous files kept as *.v<k>.*; EXPERIMENTS.md updated.")
    return 0


def _is_run_folder(run_dir: Path) -> bool:
    return (run_dir / "grades.jsonl").exists()


def _inspect(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    if not (run_dir / "summary.json").exists() or not _is_run_folder(run_dir):
        print(f"{run_dir}: not a run folder (needs summary.json and grades.jsonl)")
        return 1
    try:
        from evals.inspect_export import export_run

        paths = export_run(run_dir, args.out)
    except ImportError:
        print("inspect_ai is not installed. Install it with: pip install inspect_ai==0.3.288 "
              "(or pip install -r requirements-dev.txt)")
        return 1
    for p in paths:
        print(p)
    print(f"View with: inspect view --log-dir {args.out}")
    return 0


def _grid(args: argparse.Namespace) -> int:
    from evals.grid import diff, grid

    for d in [args.run_dir] + ([args.diff] if args.diff else []):
        if not _is_run_folder(Path(d)):
            print(f"{d}: not a run folder (needs grades.jsonl)")
            return 1
    print(diff(args.diff, args.run_dir) if args.diff else grid(args.run_dir))
    return 0


def _retrieval(args: argparse.Namespace, command: str) -> int:
    from evals import retrieval_eval
    from evals import routing_run as rr

    dense = args.world == "dense"
    text = args.sizes or ("100,200,300" if dense else "10,30,100,300")
    try:
        sizes = [int(x) for x in _csv(text)]
    except ValueError:
        print(f"--sizes must be comma-separated integers, got {text!r}")
        return 1
    return retrieval_eval.run(
        split=args.split, sizes=sizes, embedder_name=args.embedder, descriptions_source=args.descriptions,
        queries=args.queries, purpose=args.purpose or ("retrieval-dense" if dense else ""), command=command,
        out_root=args.out_root or rr.RESULTS_DIR, experiments=args.experiments, world_kind=args.world,
        paraphrases_path=args.paraphrases)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.run")
    sub = parser.add_subparsers(dest="command", required=True)
    bc = sub.add_parser("build-cases", help="generate evals/cases/v1 and its manifest")
    bc.add_argument("--paraphrase", action="store_true", help="rewrite template messages with the dev model (costs money)")
    bc.add_argument("--yes", action="store_true", help="confirm the estimated spend")
    bc.add_argument("--force-unfreeze", action="store_true", help="allow overwriting a frozen case set")
    bc.add_argument("--out", type=Path, default=V1_DIR, help=argparse.SUPPRESS)
    b2 = sub.add_parser("build-cases-v2", help="derive evals/cases/v2 from the frozen v1 set (no API calls)")
    b2.add_argument("--force-unfreeze", action="store_true", help="allow overwriting a frozen case set")
    b2.add_argument("--src", type=Path, default=V1_DIR, help=argparse.SUPPRESS)
    b2.add_argument("--out", type=Path, default=V2_DIR, help=argparse.SUPPRESS)
    fc = sub.add_parser("freeze-cases", help="verify the case set against its manifest and mark it frozen")
    fc.add_argument("--dir", type=Path, default=CASES_DIR)
    rt = sub.add_parser("routing", help="run frozen cases through the IA loop on a real model (costs money)")
    rt.add_argument("--modes", required=True, help="comma-separated roster modes, e.g. legacy")
    rt.add_argument("--sizes", required=True, help="comma-separated roster sizes, e.g. 10,300")
    rt.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    rt.add_argument("--runs", type=int, default=1)
    rt.add_argument("--model", default=None, help="OpenRouter model id (default: Settings.eval_dev_model)")
    rt.add_argument("--cases", default=None, help="comma-separated case ids (within --split)")
    rt.add_argument("--max-cost", type=float, default=None, help="stop before actual spend would exceed this (USD, default 35)")
    rt.add_argument("--concurrency", type=int, default=None, help="case-runs in flight (default 4)")
    rt.add_argument("--purpose", default="", help="why this run exists; names the run folder")
    rt.add_argument("--descriptions", default="regen", choices=["regen", "world"],
                    help="full mode's card descriptions: regenerated file (default) or the world's own")
    rt.add_argument("--embedder", default="fastembed", choices=["fastembed", "hashing"],
                    help="hybrid mode's embedder: fastembed (production's, default) or hashing (offline)")
    rt.add_argument("--yes", action="store_true", help="confirm the estimated spend")
    rt.add_argument("--cases-dir", type=Path, default=CASES_DIR, help=argparse.SUPPRESS)
    rt.add_argument("--out-root", type=Path, default=None, help=argparse.SUPPRESS)
    rg = sub.add_parser("regrade", help="re-grade a finished run folder with the current grader (no LLM calls)")
    rg.add_argument("run_dir", type=Path)
    rg.add_argument("--cases-dir", type=Path, default=None, help=argparse.SUPPRESS)
    ins = sub.add_parser("inspect", help="export a run folder to Inspect AI logs (no LLM calls)")
    ins.add_argument("run_dir", type=Path)
    ins.add_argument("--out", type=Path, default=Path("evals/inspect_logs"))
    gr = sub.add_parser("grid", help="print the case x N pass grid of a run, or its diff against another run")
    gr.add_argument("run_dir", type=Path)
    gr.add_argument("--diff", type=Path, default=None, metavar="BASELINE_RUN_DIR",
                    help="baseline run: print what changed from it to run_dir (BASELINE -> RUN)")
    rv = sub.add_parser("retrieval", help="score search_agents on the cases at several roster sizes (offline, free)")
    rv.add_argument("--split", default="dev", choices=["dev", "test"], help="test runs once, on the final config")
    rv.add_argument("--sizes", default=None, help="comma-separated roster sizes (default 10,30,100,300; dense 100,200,300)")
    rv.add_argument("--world", default="base", choices=["base", "dense"], help="dense: the two-heavy-contacts stress roster")
    rv.add_argument("--paraphrases", type=Path, default=None, help=argparse.SUPPRESS)
    rv.add_argument("--embedder", default="hashing", choices=["hashing", "fastembed"])
    rv.add_argument("--descriptions", default="regen", choices=["regen", "world"])
    rv.add_argument("--queries", default="all", choices=["frozen", "template", "all"])
    rv.add_argument("--purpose", default="", help="why this run exists; names the run folder")
    rv.add_argument("--out-root", type=Path, default=None, help=argparse.SUPPRESS)
    rv.add_argument("--experiments", type=Path, default=None, help=argparse.SUPPRESS)
    sp_ = sub.add_parser("stress-paraphrase", help="paraphrase the 48 dense-roster topics (costs a few cents)")
    sp_.add_argument("--yes", action="store_true", help="confirm the estimated spend")
    sp_.add_argument("--max-cost", type=float, default=None, help="refuse / stop beyond this spend (USD, default 0.25)")
    sp_.add_argument("--force", action="store_true", help="overwrite an existing dense_paraphrases.json")
    sp_.add_argument("--out", type=Path, default=None, help=argparse.SUPPRESS)
    rd = sub.add_parser("regen-descriptions", help="regenerate world descriptions with the real updater (costs money)")
    rd.add_argument("--yes", action="store_true", help="confirm the estimated spend")
    rd.add_argument("--max-cost", type=float, default=None, help="refuse / stop beyond this spend (USD, default 1)")
    rd.add_argument("--world", type=Path, default=WORLD_PATH, help=argparse.SUPPRESS)
    rd.add_argument("--out", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.command == "regen-descriptions":
        from evals import regen_descriptions as rd_mod

        return rd_mod.run(args.world, args.out or rd_mod.OUT_PATH, yes=args.yes, max_cost=args.max_cost)

    if args.command == "stress-paraphrase":
        from evals import stress_paraphrase as sp_mod

        return sp_mod.run(args.out or sp_mod.OUT_PATH, yes=args.yes, max_cost=args.max_cost, force=args.force)

    if args.command == "regrade":
        return _regrade(args)

    if args.command == "inspect":
        return _inspect(args)

    if args.command == "grid":
        return _grid(args)

    if args.command == "retrieval":
        return _retrieval(args, "python -m evals.run " + shlex.join(sys.argv[1:] if argv is None else argv))

    if args.command == "routing":
        command = "python -m evals.run " + shlex.join(sys.argv[1:] if argv is None else argv)
        return _routing(args, command)

    if args.command == "build-cases-v2":
        try:
            build_cases_v2(args.src, args.out, force_unfreeze=args.force_unfreeze)
        except CaseSetError as e:
            print(e)
            return 1
        return 0

    if args.command == "freeze-cases":
        try:
            manifest = freeze_case_set(args.dir, frozen_on=datetime.now(timezone.utc).date().isoformat())
        except CaseSetError as e:
            print(e)
            return 1
        print(f"Froze {manifest['n_cases']} cases in {args.dir} (frozen_on {manifest['frozen_on']})")
        return 0

    if is_frozen(args.out) and not args.force_unfreeze:
        print(f"{args.out} is frozen; refusing to overwrite it (pass --force-unfreeze to regenerate).")
        return 1
    model = None
    if args.paraphrase:
        from server.config import get_settings
        model = get_settings().eval_dev_model
        world = load_world(WORLD_PATH)
        n, prompt, completion, cost = estimate_paraphrase(expand(world, load_cases(EXAMPLES), seed=SEED), model)
        print(f"Estimated cost: ${cost:.4f} for {n} rewrites with {model} "
              f"(~{prompt} prompt + ~{completion} completion tokens, incl. retry allowance)")
        if not args.yes:
            print("Refusing to run without --yes.")
            return 2
    build_cases(args.out, paraphrase_cases=args.paraphrase, model=model, force_unfreeze=args.force_unfreeze)
    manifest = json.loads((Path(args.out) / "MANIFEST.json").read_text())
    print(f"Wrote {manifest['n_cases']} cases and MANIFEST.json to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
