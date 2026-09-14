"""Tiny API + static host for the eval UI.

    .venv/bin/python evals/ui/server.py            # serves API on :8765 and the built app from ui/dist
    (dev)  cd evals/ui && npm run dev              # Vite on :5173 proxies /api to :8765

Reads evals/e2e/cases.json and evals/e2e/results/<run>/ directly; nothing is written.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
E2E = HERE.parent / "e2e"
CASES = E2E / "cases.json"
RESULTS = E2E / "results"
DIST = HERE / "dist"

app = FastAPI(title="OpenPoke eval UI")


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(404, f"{path.name} not found")
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"{path.name}: {exc}")


def _resolve(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mirror run_e2e.resolve_cases so the UI sees the same cases the runner does."""
    import copy
    by_id = {c["id"]: c for c in raw}
    out = []
    for c in raw:
        if "extends" in c:
            base = copy.deepcopy(by_id[c["extends"]])
            base.update({k: v for k, v in c.items() if k != "extends"})
            base["extends_from"] = c["extends"]
            c = base
        if c.pop("strip_worker_filler", False):
            c["worker_logs"] = {a: [e for e in es if not e.get("filler")] for a, es in c.get("worker_logs", {}).items()}
            c["worker_logs"] = {a: es for a, es in c["worker_logs"].items() if es} or None
        out.append(c)
    return out


def _expected_cells(data: Dict[str, Any], runs: List[Dict[str, Any]]) -> int:
    case_count = len({r.get("case_id") for r in runs if r.get("case_id")})
    strategy_count = len(data.get("strategies") or [])
    size_count = 1 if data.get("mode") == "scenario" else len(data.get("sizes") or [])
    return case_count * strategy_count * size_count


@app.get("/api/cases")
def cases() -> Dict[str, Any]:
    data = _load(CASES)
    data["cases"] = _resolve(data.get("cases", []))
    return data


@app.get("/api/runs")
def runs() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not RESULTS.exists():
        return out
    for d in sorted(RESULTS.iterdir(), reverse=True):
        f = d / "results.json"
        if not d.is_dir() or not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        rs = data.get("runs", [])
        case_ids = {r.get("case_id") for r in rs if r.get("case_id")}
        expected = _expected_cells(data, rs)
        by_strategy: Dict[str, Dict[str, int]] = {}
        for r in rs:
            s = by_strategy.setdefault(r.get("strategy", "?"), {"total": 0, "passed": 0, "wall_ms": 0})
            s["total"] += 1
            s["passed"] += int(bool(r.get("success")))
            s["wall_ms"] += int(r.get("wall_ms") or 0)
        out.append({
            "id": d.name,
            "label": data.get("label", ""),
            "model": data.get("model"),
            "judge_model": data.get("judge_model"),
            "context_window": data.get("context_window"),
            "sizes": data.get("sizes"),
            "strategies": data.get("strategies"),
            "generated_at": data.get("generated_at"),
            "total": len(rs),
            "passed": sum(1 for r in rs if r.get("success")),
            "by_strategy": by_strategy,
            "cases": sorted(case_ids),
            "in_progress": len(rs) < expected,
        })
    return out


@app.get("/api/runs/{run_id}")
def run(run_id: str) -> Dict[str, Any]:
    if "/" in run_id or ".." in run_id:
        raise HTTPException(400, "bad id")
    return _load(RESULTS / run_id / "results.json")


@app.get("/api/runs/{run_id}/trace/{name}")
def trace(run_id: str, name: str) -> Dict[str, Any]:
    if any(".." in p or "/" in p for p in (run_id, name)):
        raise HTTPException(400, "bad path")
    return _load(RESULTS / run_id / "traces" / name)


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        target = DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
