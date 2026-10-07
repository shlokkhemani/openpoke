"""Presentation-proof harness (deep dive §29.1): every scenario in both modes against the real server + lab mock.

Usage (from analysis/lab):
    ../../.venv-lab/bin/python ltm_demo/run_demo.py                      # 4 proofs x {baseline, ltm} + index.json
    ../../.venv-lab/bin/python ltm_demo/run_demo.py --scenario privacy --mode ltm --extractor llm \
        --out results/ltm_demo/llm_extractor                            # step 11: extractor-capture check

Reads only public surfaces: HTTP APIs, data files, mock-OpenRouter captures, and the gated debug endpoints.
Writes results/ltm_demo/{scenario}.{mode}.json + index.json; exits 1 if any gated assertion fails or is missing.
NOTE: fresh_stack() wipes server/data/ and analysis/lab/state/ (handoff C16). Never run against a checkout with real data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))
sys.path.insert(0, str(HERE))

import httpx  # noqa: E402

import run_experiments as rx  # noqa: E402  (stack helpers; main() is guarded)
from contract import NODES, SCHEMA, INDEX_SCHEMA, _memory_module, p0_scrub, prohibited_kinds, validate_trace  # noqa: E402
from scenarios import BONUS, SCENARIOS, A, Scenario, has, required_ids  # noqa: E402

REPO = rx.REPO
DATA = rx.DATA
STATE = rx.STATE
API = rx.API
RESULTS = LAB / "results" / "ltm_demo"
MEMORY_DIR = DATA / "memory"
SYSTEM_PROMPT_FILE = REPO / "server" / "agents" / "interaction_agent" / "system_prompt.md"
SECTION_TAGS = ("conversation_history", "long_term_memory", "memory_notice", "active_agents", "new_user_message",
                "new_agent_message")
LTM_EDGES = [["conversation", "ingress_scrub"], ["ingress_scrub", "privacy"], ["privacy", "extract"],
             ["extract", "policy"], ["policy", "consolidate"], ["policy", "ignore"], ["policy", "reject"],
             ["consolidate", "store"], ["consolidate", "supersede"], ["consolidate", "fence_drop"],
             ["store", "retrieve"], ["retrieve", "agent"], ["conversation", "delete"]]
BASELINE_EDGES = [["conversation", "raw_persistence"], ["raw_persistence", "working_memory"],
                  ["working_memory", "broad_context"], ["broad_context", "agent"]]
STORE_NODES = (("poke_conversation.log", "raw_persistence"), ("poke_working_memory.log", "working_memory"),
               ("interaction_payload", "broad_context"))


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def git_dirty() -> bool:
    """Uncommitted changes in the code under test (reported separately: 'sha+dirty' trips the entropy detector)."""
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--", "server", "analysis/lab/ltm_demo",
                              "analysis/lab/mock_openrouter.py"], cwd=REPO, capture_output=True, text=True).stdout
        return bool(out.strip())
    except Exception:
        return True


# ---------------------------------------------------------------------------------------------- HTTP helpers


def await_idle(include_delayed: bool = True) -> None:
    r = httpx.post(API + "/memory/debug/test/await-idle", json={"include_delayed": include_delayed, "timeout_s": 10},
                   timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"await-idle failed: {r.status_code} {r.text}")


def latest_trace_id() -> str:
    return httpx.get(API + "/memory/debug/traces", params={"limit": 1}, timeout=10).json()[0]["trace_id"]


def get_trace(trace_id: str) -> Dict[str, Any]:
    r = httpx.get(API + f"/memory/debug/trace/{trace_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def get_state() -> Dict[str, Any]:
    r = httpx.get(API + "/memory/debug/state", timeout=10)
    r.raise_for_status()
    return r.json()


def read_files() -> Dict[str, str]:
    conv = DATA / "conversation"
    def rd(p: Path) -> str:
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    return {"conversation": rd(conv / "poke_conversation.log"), "working_memory": rd(conv / "poke_working_memory.log")}


def union_files(snapshots: Dict[int, Dict[str, str]]) -> Dict[str, str]:
    """Every line each file held at any step (DELETE /chat/history truncates them mid-run). The data dir is wiped at
    run start, so every line is 'newly written' (deep dive §29.4)."""
    out: Dict[str, str] = {}
    for key in ("conversation", "working_memory"):
        seen: Dict[str, None] = {}
        for i in sorted(snapshots):
            for line in snapshots[i][key].splitlines():
                seen.setdefault(line, None)
        out[key] = "\n".join(seen)
    return out


# ---------------------------------------------------------------------------------------------- payload analysis


def user_content(body: Dict[str, Any]) -> str:
    return next((m.get("content") or "" for m in body.get("messages", []) if m.get("role") == "user"), "")


def system_content(body: Dict[str, Any]) -> str:
    return next((m.get("content") or "" for m in body.get("messages", []) if m.get("role") == "system"), "")


def split_sections(content: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tag in SECTION_TAGS:
        bodies = re.findall(rf"<{tag}>(.*?)</{tag}>", content, re.S)
        if bodies:
            out[tag] = "\n".join(bodies)
    return out


def classify_payload(content: str, values: Dict[str, str]) -> Dict[str, Any]:
    sections = split_sections(content)
    flags = lambda s: {f"contains_{k}": has(v, s) for k, v in values.items()}  # noqa: E731
    out: Dict[str, Any] = {"sections": {name: {"present": True, **flags(body)} for name, body in sections.items()}}
    out.update({f"contains_{k}": any(has(v, b) for b in sections.values()) for k, v in values.items()})
    return out


class Ctx:
    """Harness observations handed to the scenario assertion functions."""

    def __init__(self, mode: str, turn_caps: Dict[int, Dict[str, Any]], all_caps: List[Dict[str, Any]],
                 files_final: Dict[str, str], db_bytes: Dict[str, bytes], memory_dir_exists: bool):
        self.mode = mode
        self.turn_caps = turn_caps
        self.all_caps = all_caps
        self.files_final = files_final
        self.db_bytes = db_bytes
        self.memory_dir_exists = memory_dir_exists
        self.system_prompt_file = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
        self.sha = sha

    def payload(self, i: int) -> str:
        return user_content(self.turn_caps.get(i, {}))

    @staticmethod
    def section(text: str, tag: str) -> str:
        return split_sections(text).get(tag, "")

    def ltm_section(self, i: int) -> str:
        return self.section(self.payload(i), "long_term_memory")

    def interaction_bodies(self) -> List[Dict[str, Any]]:
        return [c["body"] for c in self.all_caps if c["category"] == "interaction_agent"]

    def interaction_user_contents(self) -> List[str]:
        return [user_content(b) for b in self.interaction_bodies()]

    def interaction_system_prompts(self) -> List[str]:
        return [system_content(b) for b in self.interaction_bodies()]

    def sql_rows(self, sql: str, params=()) -> List[Dict[str, Any]]:
        db = MEMORY_DIR / "ltm.db"
        if not db.exists():
            return []
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def sql_table_text(self, like: str) -> str:
        db = MEMORY_DIR / "ltm.db"
        if not db.exists():
            return ""
        conn = sqlite3.connect(str(db))
        try:
            names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?", (like,))]
            chunks = []
            for n in names:
                for row in conn.execute(f'SELECT * FROM "{n}"'):
                    chunks.append(json.dumps([x.decode("latin-1") if isinstance(x, bytes) else x for x in row]))
            return "\n".join(chunks)
        finally:
            conn.close()


# ---------------------------------------------------------------------------------------------- baseline lane


def observe_baseline(i: int, files: Dict[str, str], payload: str, values: Dict[str, str], replied: bool):
    pipeline, rows = [], []
    texts = {"poke_conversation.log": files["conversation"], "poke_working_memory.log": files["working_memory"],
             "interaction_payload": payload}
    for seq, (store, node) in enumerate(STORE_NODES):
        contains = {k: has(v, texts[store]) for k, v in values.items()}
        present = [k for k, v in contains.items() if v]
        rows.append({"turn_index": i, "store": store, "node": node, "contains": contains})
        pipeline.append(_obs_entry(i, seq, node, "contains: " + (", ".join(present) or "none"), {"store": store,
                                                                                                "contains": contains}))
    pipeline.append(_obs_entry(i, 3, "agent", "reply received" if replied else "no reply", {"replied": replied}))
    return pipeline, rows


def _obs_entry(i, seq, node, output, detail):
    return {"turn_index": i, "trace_id": None, "seq": seq, "stage": node, "node": node, "candidate_id": None,
            "memory_id": None, "input_safe": None, "output_safe": output, "decision": None, "reason_codes": [],
            "reason": None, "scores": None, "refs": {}, "detail": detail, "ts": None, "source": "harness_observation"}


# ---------------------------------------------------------------------------------------------- canary scan

LTM_SINKS_ZERO = ("ltm.db", "ltm.db-wal", "ltm.db-shm", "sql:memories_fts*", "sql:memory_events", "events_jsonl",
                  "llm:memory_extractor")


def expectation(sc: Scenario, mode: str, canary: str, sink: str) -> str:
    if mode == "baseline":
        return "observed"
    if sc.name == "privacy" and canary == "SECRET:API_KEY":
        return "zero"
    if sc.name == "selective" and sink in ("ltm.db", "ltm.db-wal", "sql:memory_events"):
        return "debug_retained_7d"  # ignored clause text in dev-mode events only (D25), cleared by the 7-day sweep
    if sink.startswith("ltm_block") or sink in LTM_SINKS_ZERO:
        if sc.name == "conflict" and sink in ("ltm.db", "ltm.db-wal", "sql:memories_fts*", "sql:memory_events"):
            return "retained_superseded"  # superseded content kept 30 d at rest, never retrievable (D11)
        return "zero"
    if sink == "trace_file":
        return "zero" if sc.name == "privacy" else "by_design"
    if sink == "server_stdout":
        return "zero"
    return "by_design"  # short-term history and payloads are unchanged by design (§24.1)


def scan_sinks(sc: Scenario, mode: str, ctx: Ctx, doc: Dict[str, Any]) -> Dict[str, Any]:
    stdout = (STATE / "server_stdout.log").read_text(errors="replace") if (STATE / "server_stdout.log").exists() else ""
    fts_text = ctx.sql_table_text("memories_fts%")
    events_text = ctx.sql_table_text("memory_events")
    extractor = [json.dumps(c["body"]) for c in ctx.all_caps if c["category"] == "memory_extractor"]
    interaction = [json.dumps(b) for b in ctx.interaction_bodies()]
    trace_text = json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False)
    probes = [t for t in doc["turns"] if t["kind"] == "probe"]
    sinks = []
    for label, value in sc.canaries.items():
        vb = value.encode()

        def add(sink: str, hits: int, **extra: Any) -> None:
            sinks.append({"sink": sink, "canary": label, "hits": hits, "expected": expectation(sc, mode, label, sink),
                          **extra})

        for name in ("ltm.db", "ltm.db-wal", "ltm.db-shm"):
            blob = ctx.db_bytes.get(name)
            add(name, blob.count(vb) if blob is not None else 0, present=blob is not None)
        add("sql:memories_fts*", fts_text.count(value), present=bool(fts_text) or (MEMORY_DIR / "ltm.db").exists())
        add("sql:memory_events", events_text.count(value), present=(MEMORY_DIR / "ltm.db").exists())
        add("events_jsonl", 0, present=False)  # JSONL sink not enabled in the gated run
        add("llm:memory_extractor", sum(x.count(value) for x in extractor), n_captures=len(extractor))
        add("llm:interaction_agent", sum(x.count(value) for x in interaction), n_captures=len(interaction))
        for t in probes:
            add(f"ltm_block:{t['probe']}:{t['turn_index']}", ctx.ltm_section(t["turn_index"]).count(value))
        add("file:poke_conversation.log", ctx.files_final["conversation"].count(value))
        add("file:poke_working_memory.log", ctx.files_final["working_memory"].count(value))
        add("server_stdout", stdout.count(value))
        add("trace_file", trace_text.count(value))
    return {"canaries": list(sc.canaries), "sinks": sinks}


# ---------------------------------------------------------------------------------------------- one run


def new_doc(sc: Scenario, mode: str, run_id: str, extractor: str) -> Dict[str, Any]:
    ltm = mode == "ltm"
    return {
        "schema": SCHEMA, "scenario": sc.name, "mode": mode,
        "meta": {"run_id": run_id, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "git_commit": git_commit(), "git_dirty": git_dirty(),
                 "flags": {"OPENPOKE_LTM_ENABLED": ltm, "OPENPOKE_INGRESS_SCRUB": ltm, "OPENPOKE_LTM_DEBUG": ltm,
                           "OPENPOKE_LTM_DEBUG_EVENTS": ltm, "OPENPOKE_LTM_TEST_HOOKS": ltm,
                           "OPENPOKE_LTM_EXTRACTOR": extractor if ltm else None},
                 "llm": "mock", "extractor": ("rules-0.1" if extractor == "rules" else "llm-0.1") if ltm else None,
                 "policy": "policy-0.1" if ltm else None, "headline_probe": sc.headline_probe,
                 "python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
        "flow_graph": {"lane": mode, "nodes": NODES[mode], "edges": LTM_EDGES if ltm else BASELINE_EDGES},
        "turns": [], "pipeline": [], "memory_state": [], "retrieval": [], "retrieved": [], "model_context": {},
        "probes": [], "baseline_observations": [], "canary_scan": {"canaries": [], "sinks": []}, "assertions": [],
    }


def env_for(mode: str, extractor: str) -> Dict[str, str]:
    on = "true" if mode == "ltm" else "false"
    env = {"OPENPOKE_LTM_ENABLED": on, "OPENPOKE_INGRESS_SCRUB": on, "OPENPOKE_LTM_DEBUG": "1" if mode == "ltm" else "0",
           "OPENPOKE_LTM_DEBUG_EVENTS": "1" if mode == "ltm" else "0",
           "OPENPOKE_LTM_TEST_HOOKS": "1" if mode == "ltm" else "0"}
    if mode == "ltm":
        env["OPENPOKE_LTM_EXTRACTOR"] = extractor
    return env


def run(sc: Scenario, mode: str, run_id: str, out_dir: Path, extractor: str = "rules") -> Dict[str, Any]:
    ltm = mode == "ltm"
    env = env_for(mode, extractor)
    rx.fresh_stack(env)
    try:
        doc = new_doc(sc, mode, run_id, extractor)
        turn_caps: Dict[int, Dict[str, Any]] = {}
        files_after: Dict[int, Dict[str, str]] = {}
        session = 1
        for i, step in enumerate(sc.steps):
            turn: Dict[str, Any] = {"turn_index": i, "session": f"s{session}", "kind": step.kind,
                                    "text_safe": p0_scrub(step.text) if step.text else None, "path": [],
                                    "outcomes": []}
            if step.probe:
                turn["probe"] = step.probe
                turn["label"] = step.label or step.probe
            if step.kind == "hook":
                if ltm:
                    r = httpx.post(API + "/memory/debug/test/ingest-delay", json=step.body, timeout=10)
                    r.raise_for_status()
                    turn["hook"] = step.body
                else:
                    turn["skipped"] = "baseline has no test hooks"
            elif step.kind in ("new_conversation", "restart"):
                if ltm:
                    await_idle()
                rx.wait_idle(quiet=0.3)
                if step.kind == "new_conversation":
                    r = httpx.delete(API + "/chat/history", timeout=10)
                    r.raise_for_status()
                else:
                    rx.stop("server")
                    rx.start_server(env)
                session += 1
                turn["session"] = f"s{session}"
            elif step.kind == "wait_duplicate":
                if ltm:
                    await_idle(include_delayed=True)
                else:
                    rx.wait_idle(quiet=0.3)
            else:  # setup / probe: a real chat turn
                n = len(rx.captures())
                rx.send(step.text, quiet=0.3)
                if ltm:
                    await_idle(include_delayed=step.await_mode == "all")
                rx.wait_idle(quiet=0.3)
                caps = [c for c in rx.captures()[n:] if c["category"] == "interaction_agent"]
                body = caps[0]["body"] if caps else {}
                turn_caps[i] = body
                if ltm:
                    turn["trace_id"] = latest_trace_id()
                else:
                    turn["path"] = list(NODES["baseline"])
                    pipe, rows = observe_baseline(i, read_files(), user_content(body), sc.values, bool(caps))
                    doc["pipeline"] += pipe
                    doc["baseline_observations"] += rows
                if step.kind == "probe":
                    doc["probes"].append({"probe": step.probe, "label": turn["label"], "turn_index": i,
                                          "model_context": classify_payload(user_content(body), sc.values)})
            files_after[i] = read_files()
            if ltm:
                doc["memory_state"].append({"after_turn": i, **get_state()})
            doc["turns"].append(turn)

        if ltm:
            await_idle()
            finalise_ltm(doc, sc)

        db_bytes = {}
        for name in ("ltm.db", "ltm.db-wal", "ltm.db-shm"):
            p = MEMORY_DIR / name
            if p.exists():
                db_bytes[name] = p.read_bytes()
        ctx = Ctx(mode, turn_caps, rx.captures(), union_files(files_after), db_bytes, MEMORY_DIR.exists())
        ctx.files_after = files_after
        set_headline(doc, sc)
        doc["canary_scan"] = scan_sinks(sc, mode, ctx, doc)
        doc["assertions"] = sc.assertions[mode](doc, ctx)
        if extractor == "llm":
            doc["assertions"] += llm_extractor_assertions(doc)
        finish_contract(doc)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{sc.name}.{mode}.json"
        text = json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")
        return doc
    finally:
        rx.stop("server")
        rx.stop("mock")


def finalise_ltm(doc: Dict[str, Any], sc: Scenario) -> None:
    """Re-assemble every turn trace at the end, so late events (the stale duplicate's fence_drop) are included."""
    by_trace = {t["trace_id"]: t["turn_index"] for t in doc["turns"] if t.get("trace_id")}
    steps = {i: s for i, s in enumerate(sc.steps)}
    for t in doc["turns"]:
        if not t.get("trace_id"):
            continue
        tr = get_trace(t["trace_id"])
        t["path"] = tr["path"]
        t["outcomes"] = tr["outcomes"]
        for p in tr["pipeline"]:
            doc["pipeline"].append({"turn_index": t["turn_index"], **p})
        if tr["retrieval"]:
            step = steps[t["turn_index"]]
            r = {k: v for k, v in tr["retrieval"].items() if k not in ("trace_id",)}
            doc["retrieval"].append({"turn_index": t["turn_index"], "probe": step.probe, "label": step.label, **r})
    for snap in doc["memory_state"]:
        for m in snap["memories"]:
            for h in m["status_history"]:
                h["turn_index"] = by_trace.get(h.get("trace_id"))


def set_headline(doc: Dict[str, Any], sc: Scenario) -> None:
    probe = next((p for p in doc["probes"] if p["probe"] == sc.headline_probe), doc["probes"][0] if doc["probes"] else None)
    if not probe:
        return
    mc = {"probe": probe["probe"], "turn_index": probe["turn_index"], **probe["model_context"]}
    if probe["probe"] == "same_session" and doc["mode"] == "ltm":
        mc["note"] = "same-session short-term history unchanged by design (see design §24.1)"
    doc["model_context"] = mc
    r = next((x for x in doc["retrieval"] if x["turn_index"] == probe["turn_index"]), None)
    if r:
        texts = {p["memory_id"]: p["output_safe"] for p in doc["pipeline"]
                 if p["stage"] == "retrieve.rank" and p["turn_index"] == probe["turn_index"]}
        doc["retrieved"] = [{"alias": s["alias"], "memory_id": s["memory_id"], "text": texts.get(s["memory_id"])}
                            for s in r["selected"]]


def llm_extractor_assertions(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    ext = [s for s in doc["canary_scan"]["sinks"] if s["sink"] == "llm:memory_extractor"]
    secret = [s for s in ext if s["canary"] == "SECRET:API_KEY"]
    return [
        A("llm_extractor.extractor_called", "the LLMExtractor really called the (mock) model",
          bool(secret) and secret[0].get("n_captures", 0) > 0, expected=">0",
          actual=secret[0].get("n_captures") if secret else 0),
        A("llm_extractor.zero_secret_in_extractor_captures", "extractor captures hold no secret (LLM_SAFE only)",
          bool(secret) and secret[0]["hits"] == 0, expected=0, actual=secret[0]["hits"] if secret else None),
    ]


def finish_contract(doc: Dict[str, Any]) -> None:
    doc["assertions"] += [A("contract.valid", "validate_trace() passes", True),
                          A("contract.leak_free", "no prohibited-class pattern anywhere in this file", True)]
    problems = validate_trace(doc)
    kinds = prohibited_kinds(json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False))
    doc["assertions"][-2].update({"passed": not problems, "expected": [], "actual": problems,
                                  "evidence": {"schema": SCHEMA}})
    doc["assertions"][-1].update({"passed": not kinds, "expected": [], "actual": kinds,
                                  "evidence": {"method": "ingress detectors over the serialised file (§24.1)"}})


# ---------------------------------------------------------------------------------------------- main


def gate(files: List[Path], gated_ids=None) -> List[Dict[str, str]]:
    failed = []
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        by_id = {a["id"]: a for a in doc["assertions"]}
        need = gated_ids(doc) if gated_ids else required_ids(doc["scenario"], doc["mode"])
        for aid in need:
            if aid not in by_id or not by_id[aid]["passed"]:
                failed.append({"file": f.name, "assertion_id": aid})
        if gated_ids is None:
            for a in doc["assertions"]:
                if not a["passed"] and a["id"] not in need:
                    failed.append({"file": f.name, "assertion_id": a["id"]})
        if validate_trace(doc):
            failed.append({"file": f.name, "assertion_id": "contract.valid"})
    return failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", nargs="*", default=list(SCENARIOS))
    ap.add_argument("--mode", nargs="*", default=["baseline", "ltm"])
    ap.add_argument("--extractor", default="rules", choices=["rules", "llm"])
    ap.add_argument("--out", default=str(RESULTS))
    ap.add_argument("--bonus", action="store_true", help="also run the (ungated) poisoning scenario")
    args = ap.parse_args()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = (LAB / out_dir).resolve()
    run_id = _memory_module("models").new_id("run")  # 'run_' + ULID (LTM_BLOCKERS.md B1)
    all_sc = {**SCENARIOS, **BONUS}
    files: List[Path] = []
    for name in args.scenario:
        for mode in args.mode:
            t0 = time.time()
            run(all_sc[name], mode, run_id, out_dir, args.extractor)
            files.append(out_dir / f"{name}.{mode}.json")
            print(f"[run_demo] {name}.{mode}: {time.time() - t0:.1f}s", flush=True)
    bonus_files: List[Path] = []
    if args.bonus:
        bonus_dir = out_dir / "bonus"
        for mode in args.mode:
            run(BONUS["poisoning"], mode, run_id, bonus_dir, args.extractor)
            bonus_files.append(bonus_dir / f"poisoning.{mode}.json")

    if args.extractor == "llm":
        gated = lambda doc: ["llm_extractor.extractor_called", "llm_extractor.zero_secret_in_extractor_captures",  # noqa: E731
                             "privacy.secret_zero_hits_all_sinks", "privacy.email_not_in_ltm",
                             "privacy.no_secret_in_any_interaction_payload", "contract.valid", "contract.leak_free"]
        failed = gate(files, gated)
    else:
        failed = gate(files)
    index = {"schema": INDEX_SCHEMA, "run_id": run_id,
             "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "git_commit": git_commit(),
             "git_dirty": git_dirty(), "extractor": args.extractor, "files": [f.name for f in files],
             "bonus_files": [str(f.relative_to(out_dir)) for f in bonus_files], "gate_passed": not failed,
             "failed": failed}
    (out_dir / "index.json").write_text(json.dumps(index, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gate_passed": not failed, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
