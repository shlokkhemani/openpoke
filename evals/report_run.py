"""``report.md`` for one routing run, and its line in ``EXPERIMENTS.md``, from ``summary.json``.

The report is generated and brief; its last section, "What we learned", is left empty for a person
to fill in after reading the run. ``render_report`` also reads summaries written before the
2026-11-07 runner fixes (no error kinds, reused-copy counts or unmetered attempts).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

EXPERIMENTS_HEADER = (
    "# Experiments\n\n"
    "One line per routing run, appended by `python -m evals.run routing`. Each run folder has a `report.md`.\n\n"
    "| date | run folder | purpose | headline (pass rate per mode × N) | cost |\n"
    "|---|---|---|---|---|\n"
)
WHAT_WE_LEARNED = "## What we learned"


def _pct(cell: dict[str, Any]) -> str:
    if not cell["graded"]:
        return "–"
    return f"{cell['rate']:.0%} ({cell['passed']}/{cell['graded']})"


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def headline(summary: dict[str, Any]) -> str:
    """``legacy N=10 75% (12/16), N=300 50% (8/16)``; modes separated by ``;``."""
    parts = []
    for mode in summary["modes"]:
        cells = summary["pass_rate"][mode]
        parts.append(f"{mode} " + ", ".join(f"N={n} {_pct(cells[str(n)])}" for n in summary["sizes"]))
    return "; ".join(parts)


def _descriptions_lines(s: dict[str, Any]) -> list[str]:
    d = s.get("descriptions")
    if not d:
        return []
    if d["source"] == "world":
        return ["- **Descriptions (`full`):** world (each agent's own description)"]
    return [f"- **Descriptions (`full`):** regen, sha256 `{d['sha256']}`, covering "
            f"{d['covered']}/{d['total']} world agents"]


def render_report(s: dict[str, Any]) -> str:
    modes, sizes = s["modes"], s["sizes"]
    c, cost, lat = s["counts"], s["cost"], s["latency"]
    cols = [f"N={n}" for n in sizes]
    lines = [
        f"# Routing run: {s['purpose'] or '(no purpose given)'}",
        "",
        "## Setup",
        "",
        f"- **Purpose:** {s['purpose'] or '(none)'}",
        f"- **Command:** `{s['command']}`",
        f"- **Date (UTC):** {s['date_utc']}",
        f"- **Model:** `{s['model']}`",
        f"- **Code:** {s['git']}",
        f"- **Case set:** `{s['case_set']['dir']}` ({s['case_set']['version']}), MANIFEST sha256 "
        f"`{s['case_set']['manifest_sha256']}`, frozen_on {s['case_set']['frozen_on']}",
        f"- **Split:** {s['split']}, {s['n_cases']} cases",
        *_descriptions_lines(s),
        f"- **Grid:** modes {', '.join(modes)} × sizes {', '.join(map(str, sizes))} × {s['runs']} run(s) "
        f"= {c['planned']} case-runs",
        f"- **Outcome:** {c['graded']} graded, {c['infra_errors']} infra errors (not graded), "
        f"{c['skipped_max_cost']} skipped by the max-cost cap (${s['max_cost']:g}), {c['retried']} retried",
        *_regraded_lines(s),
        "",
        "## Cost",
        "",
        f"- Actual: **${cost['actual_usd']:.4f}** (estimate before the run: ${cost['estimated_usd']:.4f})",
        f"- Tokens: {cost['prompt_tokens']:,} prompt / {cost['completion_tokens']:,} completion (all attempts)",
        f"- Mean latency per case-run: {lat['mean_latency_s']} s; mean round trips: {lat['mean_round_trips']}",
        *_unmetered_lines(cost),
        "",
        "## Pass rate by mode × N",
        "",
        "Infra errors are excluded from the denominators; structural failures count as failures.",
        "",
        _table(["mode", *cols], [[m, *(_pct(s["pass_rate"][m][str(n)]) for n in sizes)] for m in modes]),
        "",
        "## Pass rate by category",
        "",
        _table(["category", "mode", *cols],
               [[cat, m, *(_pct(t[m][str(n)]) for n in sizes)] for cat, t in s["by_category"].items() for m in modes]),
        "",
        "## Flags",
        "",
    ]
    flag_names = sorted({f for m in modes for n in sizes for f in s["flags"][m][str(n)]})
    if flag_names:
        rows = []
        for f in flag_names:
            for m in modes:
                row = [f, m]
                for n in sizes:
                    k, g = s["flags"][m][str(n)].get(f, 0), s["pass_rate"][m][str(n)]["graded"]
                    row.append(f"{k}/{g}" if g else "–")
                rows.append(row)
        lines.append(_table(["flag", "mode", *cols], rows))
    else:
        lines.append("No flags raised.")
    lines += [
        *_search_lines(s),
        "",
        "## Structural failures",
        "",
        "A legacy dispatch by a name that several agents share (e.g. two \"Email Alice\" agents): the "
        "names-only roster cannot express the right target.",
        "",
        _table(["mode", *cols], [[m, *(s["structural"][m][str(n)] for n in sizes)] for m in modes]),
        "",
        "## Infra errors",
        "",
        "Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. "
        "Counts are case-runs.",
        "",
        _table(["mode", *cols], [[m, *(s["infra_errors"][m][str(n)] for n in sizes)] for m in modes]),
        *_error_kind_lines(s),
    ]
    if c["skipped_max_cost"]:
        lines += ["", f"**{c['skipped_max_cost']} case-runs skipped** because the max-cost cap "
                      f"(${s['max_cost']:g}) would have been crossed:", "",
                  _table(["mode", *cols], [[m, *(s["skipped"][m][str(n)] for n in sizes)] for m in modes])]
    lines += ["", "## Failing case-runs", ""]
    if s["failing"]:
        lines.append(_table(
            ["case", "category", "mode", "N", "run", "outcome", "flags", "reason"],
            [[f["case_id"], f["category"], f["mode"], f["n"], f["run_idx"], f["outcome_kind"],
              ", ".join(f["flags"]) or "–", f["reason"]] for f in s["failing"]]))
    else:
        lines.append("None.")
    lines += ["", WHAT_WE_LEARNED, ""]
    return "\n".join(lines)


def _regraded_lines(s: dict[str, Any]) -> list[str]:
    return [f"- **Regraded:** {r['date_utc'][:10]} with the current grader, without LLM calls "
            f"(before: {r['previous_headline']})" for r in s.get("regraded", [])]


def _unmetered_lines(cost: dict[str, Any]) -> list[str]:
    k = cost.get("unmetered_attempts", 0)
    if not k:
        return []
    return [f"- {k} attempt(s) got a response with no usage block; each was charged its estimate "
            f"(${cost.get('unmetered_usd', 0):.4f} of the actual total) so the cap stayed honest"]


def _search_lines(s: dict[str, Any]) -> list[str]:
    """The ``## Search`` section of a run with ``hybrid``: how often the model searched and what it found."""
    if not s.get("search"):
        return []
    sizes = s["sizes"]
    header = ["mode", "measure", *[f"N={n}" for n in sizes]]
    rows = []
    for m, by_n in s["search"].items():
        def frac(key, n):
            c = by_n[str(n)]
            return f"{c[key]}/{c['graded']}" if c["graded"] else "–"
        rows += [
            [m, "Search rate (case-runs that searched)", *(frac("searched", n) for n in sizes)],
            [m, "Search errors (calls)", *(by_n[str(n)]["search_errors"] for n in sizes)],
            [m, "Target in the initial cards", *(frac("target_in_initial", n) for n in sizes)],
            [m, "Target found only by search", *(frac("target_found_by_search", n) for n in sizes)],
        ]
    return ["", "## Search", "",
            f"Embedder: `{s.get('embedder')}`. The target is the graded case's expected agents "
            "(`retrieval_eval.expected_for`); cases without one count in neither target row.", "",
            _table(header, rows)]


def _error_kind_lines(s: dict[str, Any]) -> list[str]:
    kinds = s.get("error_kinds") or {}
    if not kinds:
        return []
    out = ["", "By kind (prefix of the error):", "", _table(["error kind", "case-runs"], sorted(kinds.items()))]
    loops = s.get("iteration_limit") or []
    if loops:
        out += ["", f"**{len(loops)} iteration-limit loop(s)** (the IA kept calling tools until the runtime's "
                    f"iteration limit, with no final answer): {', '.join(loops)}. They are excluded from the pass "
                    "rates like infra errors, but a loop is arguably a routing failure, so excluding them biases "
                    "the pass rates upward."]
    return out


def append_experiment(path: Path, s: dict[str, Any]) -> None:
    """Append one line for this run to ``EXPERIMENTS.md``, creating it with a header if missing."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(EXPERIMENTS_HEADER, encoding="utf-8")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_experiment_row(s) + "\n")


def _experiment_row(s: dict[str, Any], note: str = "") -> str:
    head = headline(s) + (f" ({note})" if note else "")
    row = [s["date_utc"][:10], s["run_folder"], s["purpose"] or "–", head, f"${s['cost']['actual_usd']:.4f}"]
    return "| " + " | ".join(_cell(x) for x in row) + " |"


def update_experiment(path: Path, s: dict[str, Any], note: str) -> None:
    """Replace this run's line in ``EXPERIMENTS.md`` (``note`` appended to the headline); append if absent."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(EXPERIMENTS_HEADER, encoding="utf-8")
    lines = path.read_text(encoding="utf-8").splitlines()
    new = _experiment_row(s, note)
    hits = [i for i, line in enumerate(lines) if f"| {s['run_folder']} |" in line]
    if hits:
        lines[hits[0]] = new
        lines = [line for i, line in enumerate(lines) if i not in hits[1:]]
    else:
        lines.append(new)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
