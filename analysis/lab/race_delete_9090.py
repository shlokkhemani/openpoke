"""Proof #4 driver: race_exec mechanism from analysis/lab/run_experiments.py, marker DELETE-RACE-9090.

Reuses the lab helpers unchanged (fresh_stack, control, scan_locations, wait_idle, history, stop).
Adds per-moment wall-clock timestamps, per-file line numbers, and GET /chat/history at every moment.
Usage: .venv-lab/bin/python race_9090.py <repo> <out.json>
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(REPO / "analysis" / "lab"))
import httpx  # noqa: E402
import run_experiments as lab  # noqa: E402

MARKER = "DELETE-RACE-9090"
MESSAGE = f"DELEGATE: note {MARKER}"


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def file_hits() -> dict:
    hits = {}
    if lab.DATA.exists():
        for f in sorted(lab.DATA.rglob("*")):
            if not f.is_file():
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            nums = [i + 1 for i, line in enumerate(lines) if MARKER in line]
            if nums:
                hits[str(f.relative_to(REPO))] = {"lines": nums, "text": [lines[n - 1] for n in nums]}
    return hits


def snapshot(label: str) -> dict:
    hist = lab.history()
    return {
        "moment": label,
        "time": ts(),
        "locations": lab.scan_locations({"marker": MARKER})["marker"],
        "file_hits": file_hits(),
        "history_api": [m for m in hist if MARKER in m.get("content", "")],
        "history_api_len": len(hist),
        "data_files": lab.data_files(),
    }


def dump_files() -> dict:
    out = {}
    for rel in ["conversation/poke_conversation.log", "conversation/poke_working_memory.log"]:
        p = lab.DATA / rel
        out[f"server/data/{rel}"] = p.read_text(encoding="utf-8").splitlines() if p.exists() else None
    ea = lab.DATA / "execution_agents"
    if ea.exists():
        for p in sorted(ea.iterdir()):
            out[str(p.relative_to(REPO))] = p.read_text(encoding="utf-8").splitlines()
    return out


timeline = []
try:
    lab.fresh_stack()
    timeline.append({"event": "lab stack up (mock :18080, OpenPoke :18001)", "time": ts()})
    lab.control(delay={"execution_agent": 4})
    timeline.append({"event": "mock execution_agent delay = 4s", "time": ts()})
    r = httpx.post(lab.API + "/chat/send", json={"messages": [{"role": "user", "content": MESSAGE}]})
    timeline.append({"event": f"POST /chat/send -> {r.status_code}", "time": ts()})
    time.sleep(2.0)
    before = snapshot("before_delete")
    r = httpx.delete(lab.API + "/chat/history")
    timeline.append({"event": f"DELETE /chat/history -> {r.status_code} {r.text}", "time": ts()})
    right_after = snapshot("immediately_after_delete")
    lab.wait_idle(quiet=3)
    timeline.append({"event": "system idle (no data/capture changes for 3s)", "time": ts()})
    after = snapshot("after_inflight_agent_finished")
    files_after = dump_files()
    caps = [{"t": datetime.fromtimestamp(c["t"]).strftime("%H:%M:%S.%f")[:-3], "category": c["category"],
             "marker_in_body": MARKER in json.dumps(c["body"])} for c in lab.captures()]
    srv_log = (lab.STATE / "server_stdout.log").read_text(errors="replace").splitlines()
finally:
    lab.stop("server"); lab.stop("mock")

Path(sys.argv[2]).write_text(json.dumps({
    "marker": MARKER, "message": MESSAGE, "timeline": timeline,
    "snapshots": [before, right_after, after], "files_after": files_after,
    "llm_captures": caps, "server_log_tail": srv_log[-40:],
}, indent=2))
print("ok")
