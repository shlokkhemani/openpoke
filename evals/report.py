"""Aggregate scored runs into the original-vs-fork report (evaluation-plan §6)."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Two-sided 95% t critical values by degrees of freedom.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
        20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048,
        29: 2.045, 30: 2.042}


def _t95(df: int) -> float:
    return _T95.get(df, 1.96)


def paired_ci(diffs: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    diffs = [d for d in diffs if d is not None]
    if len(diffs) < 2:
        return (diffs[0] if diffs else None), None, None
    mean = statistics.mean(diffs)
    half = _t95(len(diffs) - 1) * statistics.stdev(diffs) / math.sqrt(len(diffs))
    return mean, mean - half, mean + half


COMPARED_METRICS = [
    ("task_completion", "Task completion (share of runs passing all checks)", "higher"),
    ("judge", "Reply quality, judge (1–5)", "higher"),
    ("useful_reply_s", "Latency (s)", "lower"),
    ("llm_calls_per_turn", "LLM calls / turn", "lower"),
    ("prompt_tokens_per_turn", "Input tokens / turn", "lower"),
    ("completion_tokens_per_turn", "Output tokens / turn", "lower"),
    ("agents_seen_per_call", "Agents shown to Poke per call", "lower"),
    ("split", "Split rate (one goal in >1 agent)", "lower"),
]


SCENARIO_DIR = Path(__file__).with_name("scenarios")
_GOALS: Dict[str, Optional[int]] = {}


def goals_of(case_id: str) -> Optional[int]:
    """Number of separate user goals in a scenario (its `goals:` field)."""
    if not _GOALS:
        import yaml
        for path in SCENARIO_DIR.glob("*.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            _GOALS[data["id"]] = data.get("goals")
    return _GOALS.get(case_id)


def _mean(values: List[float]) -> Optional[float]:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _pct(values: List[float], q: float) -> Optional[float]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    k = (len(values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def _fmt(value: Optional[float], digits: int = 1) -> str:
    return "–" if value is None else f"{value:,.{digits}f}"


def load_results(out: Path) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """{version: {case: [result, ...]}}"""
    results: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for path in sorted(out.glob("*/*/run_*/result.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        results[data["version"]][data["case"]].append(data)
    return results


def _metric(result: Dict[str, Any], key: str) -> Optional[float]:
    if key == "judge":
        return (result.get("judge") or {}).get("score")
    if key == "task_completion":
        return 1.0 if result.get("passed") else 0.0
    if key == "split":
        goals = goals_of(result["case"])
        if goals is None:
            return None
        return 1.0 if result["metrics"].get("agents_created", 0) > goals else 0.0
    return result["metrics"].get(key)


def collapse(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Collapse k runs of one case into one row."""
    passes = [r["passed"] for r in runs]
    row: Dict[str, Any] = {
        "runs": len(runs),
        "strict_pass": all(passes),
        "flaky": any(passes) and not all(passes),
        "group": runs[0].get("group"),
        "useful_reply_samples": [s for r in runs for s in r["metrics"].get("useful_reply_samples", [])],
        "series": [r["metrics"].get("interaction_prompt_series") for r in runs],
        "case_metrics": defaultdict(list),
    }
    for key, _, _ in COMPARED_METRICS:
        row[key] = _mean([_metric(r, key) for r in runs])
    for r in runs:
        for name, value in (r.get("case_metrics") or {}).items():
            if value is not None:
                row["case_metrics"][name].append(value)
    return row


def build_report(out: Path) -> str:
    results = load_results(out)
    rows = {v: {case: collapse(runs) for case, runs in cases.items()} for v, cases in results.items()}
    data_runs = results
    orig, fork = rows.get("original", {}), rows.get("fork", {})
    shared = sorted(set(orig) & set(fork))
    lines: List[str] = [f"# OpenPoke eval report\n", f"Runs folder: `{out}`\n"]

    # ---- summary
    lines.append("## Summary (paired over cases)\n")
    lines.append(f"Cases compared: {len(shared)}. Each case value = mean of its runs; CI = paired t-interval of fork − original.\n")
    lines.append("| Metric | Original | Fork | Δ fork − original (95% CI) | Better |")
    lines.append("|---|---|---|---|---|")
    for key, label, better in COMPARED_METRICS:
        o = _mean([orig[c][key] for c in shared])
        f = _mean([fork[c][key] for c in shared])
        diffs = [fork[c][key] - orig[c][key] for c in shared if fork[c][key] is not None and orig[c][key] is not None]
        mean, lo, hi = paired_ci(diffs)
        ci = f"{_fmt(mean, 2)} [{_fmt(lo, 2)}, {_fmt(hi, 2)}]" if lo is not None else _fmt(mean, 2)
        verdict = "–"
        if lo is not None and (lo > 0 or hi < 0):
            fork_better = (mean > 0) == (better == "higher")
            verdict = "fork" if fork_better else "original"
        lines.append(f"| {label} | {_fmt(o, 2)} | {_fmt(f, 2)} | {ci} | {verdict} |")

    judge_model = None
    try:
        judge_model = json.loads((out / "config.json").read_text(encoding="utf-8")).get("judge_model")
    except (OSError, ValueError):
        pass
    lines.append("\n**Task completion** is the share of a case's runs in which every deterministic check passed: "
                 "the right reminders exist, at the right times, updated in place and owned by the right agent, "
                 "and every user message got a reply within the time limit.")
    lines.append(f"\n**Reply quality** is scored 1–5 by an LLM judge ({judge_model or 'model not recorded'}): "
                 "does what the assistant told the user match the reminders actually set, and is it clear?")

    # ---- pass / flips
    o_pass = sum(orig[c]["strict_pass"] for c in shared)
    f_pass = sum(fork[c]["strict_pass"] for c in shared)
    fixed = [c for c in shared if not orig[c]["strict_pass"] and fork[c]["strict_pass"]]
    broke = [c for c in shared if orig[c]["strict_pass"] and not fork[c]["strict_pass"]]
    lines.append("\n## Task completion by case (strict: a case passes only if all its runs pass)\n")
    lines.append(f"- Original: {o_pass}/{len(shared)} pass, {sum(orig[c]['flaky'] for c in shared)} flaky")
    lines.append(f"- Fork: {f_pass}/{len(shared)} pass, {sum(fork[c]['flaky'] for c in shared)} flaky")
    lines.append(f"- Fail → pass (fork fixed): {', '.join(fixed) or 'none'}")
    lines.append(f"- Pass → fail (fork regressed): {', '.join(broke) or 'none'}")

    errors = sorted(str(p.parent.relative_to(out)) for p in out.glob("*/*/run_*/error.txt"))
    if errors:
        lines.append("\n## Runs that errored (excluded)\n")
        lines.extend(f"- {e}" for e in errors)

    report = "\n".join(lines) + "\n"
    (out / "report.md").write_text(report, encoding="utf-8")
    return report


__all__ = ["build_report"]
