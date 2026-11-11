"""Case x N pass grid for one run folder, and a diff between two runs. Reads grades.jsonl only."""
from collections import defaultdict
from pathlib import Path

from evals.run_store import read_jsonl

Cells = dict  # (case_id, mode, n) -> (passes, runs)


def _cells(run_dir: Path) -> tuple[Cells, dict]:
    cells: dict = defaultdict(lambda: [0, 0])
    category = {}
    for g in read_jsonl(Path(run_dir) / "grades.jsonl"):
        c = cells[(g["case_id"], g["mode"], g["n"])]
        c[0] += bool(g["passed"])
        c[1] += 1
        category[g["case_id"]] = g["category"]
    return {k: tuple(v) for k, v in cells.items()}, category


def _fmt(cell, mark=True) -> str:
    return f"{cell[0]}/{cell[1]}" + (" ✗" if mark and cell[0] < cell[1] else "")


def grid(run_dir: Path) -> str:
    cells, category = _cells(run_dir)
    out = []
    for mode in sorted({k[1] for k in cells}):
        ns = sorted({k[2] for k in cells if k[1] == mode})
        cases = sorted({k[0] for k in cells if k[1] == mode})
        out += [f"{mode}", "", "case  category  " + "  ".join(str(n) for n in ns)]
        for case in cases:
            vals = [_fmt(cells[(case, mode, n)]) if (case, mode, n) in cells else "-" for n in ns]
            out.append(f"{case}  {category[case]}  " + "  ".join(vals))
        out.append("")
    return "\n".join(out)


def diff(run_a: Path, run_b: Path) -> str:
    a, _ = _cells(run_a)
    b, _ = _cells(run_b)
    changed = [f"{c} {m} {n}: {_fmt(a[(c, m, n)], False)} → {_fmt(b[(c, m, n)], False)}"
               for (c, m, n) in sorted(a.keys() & b.keys()) if a[(c, m, n)] != b[(c, m, n)]]
    only = [f"only in {Path(run).name}: {c} {m} {n} {_fmt(cs[(c, m, n)], False)}"
            for run, cs, other in ((run_a, a, b), (run_b, b, a)) for (c, m, n) in sorted(cs.keys() - other.keys())]
    return "\n".join(changed + only) if changed or only else "no changes"
