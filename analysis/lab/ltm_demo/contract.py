"""Structural validator for ``openpoke.ltm.demo_trace.v1`` (design §25, handoff §7). Stdlib only.

``validate_trace(doc) -> list[str]`` returns problems; an empty list means valid. The future UI consumes only these
files, so this is the contract it can rely on.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import types
from pathlib import Path
from typing import Any, Dict, List

SCHEMA = "openpoke.ltm.demo_trace.v1"
INDEX_SCHEMA = "openpoke.ltm.demo_trace.index.v1"
SCENARIOS = ("conflict", "privacy", "selective", "forget", "poisoning")
MODES = ("baseline", "ltm")
PROBES = ("same_session", "new_conversation", "after_restart")
NODES = {
    "baseline": ["conversation", "raw_persistence", "working_memory", "broad_context", "agent"],
    "ltm": ["conversation", "ingress_scrub", "privacy", "extract", "policy", "consolidate", "store", "ignore",
            "reject", "supersede", "delete", "fence_drop", "retrieve", "agent"],
}
TOP_LEVEL = ("schema", "scenario", "mode", "meta", "flow_graph", "turns", "pipeline", "memory_state", "retrieval",
             "retrieved", "model_context", "probes", "baseline_observations", "canary_scan", "assertions")
PIPELINE_KEYS = ("turn_index", "trace_id", "seq", "stage", "node", "candidate_id", "memory_id", "input_safe",
                 "output_safe", "decision", "reason_codes", "reason", "scores", "refs", "ts", "source")
RETRIEVAL_KEYS = ("turn_index", "probe", "query", "hard_filters", "excluded_by_filters", "candidates", "selected",
                  "ltm_block", "ltm_block_tokens")
CANDIDATE_KEYS = ("memory_id", "generators", "rel", "imp", "conf", "rec", "total", "selected", "drop_reason")
MEMORY_KEYS = ("id", "slot_key", "memory_type", "status", "canonical_text", "status_history")
CANARY_LABEL = re.compile(r"^[A-Z_]+:[A-Za-z0-9_.\-]+$")

REPO = Path(__file__).resolve().parents[3]


def _memory_module(name: str) -> types.ModuleType:
    """Import ``server/services/memory/<name>.py`` WITHOUT importing the ``server`` package (which boots the app).

    privacy / detectors / models are stdlib-only, so a synthetic parent package is enough."""
    pkg = "_ltm_memory_pkg"
    if pkg not in sys.modules:
        mod = types.ModuleType(pkg)
        mod.__path__ = [str(REPO / "server" / "services" / "memory")]  # type: ignore[attr-defined]
        sys.modules[pkg] = mod
    return importlib.import_module(f"{pkg}.{name}")


def prohibited_kinds(text: str) -> List[str]:
    """Kinds of SECRET / REGULATED_ID patterns present (the §24.1 leak guard primitive). Never returns values."""
    return sorted({f.kind for f in _memory_module("privacy").prohibited_findings(text)})


def p0_scrub(text: str) -> str:
    return _memory_module("privacy").scrub(text)[0].llm_safe


def _req(errors: List[str], cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def validate_trace(doc: Any) -> List[str]:
    e: List[str] = []
    if not isinstance(doc, dict):
        return ["document is not an object"]
    for k in TOP_LEVEL:
        _req(e, k in doc, f"missing top-level key {k!r}")
    if e:
        return e
    mode = doc["mode"]
    _req(e, doc["schema"] == SCHEMA, "schema mismatch")
    _req(e, doc["scenario"] in SCENARIOS, f"unknown scenario {doc['scenario']!r}")
    _req(e, mode in MODES, f"unknown mode {mode!r}")
    if mode not in MODES:
        return e
    nodes = NODES[mode]

    meta = doc["meta"]
    _req(e, isinstance(meta, dict) and all(k in meta for k in ("run_id", "generated_at", "git_commit", "flags",
                                                                 "llm", "headline_probe")), "meta incomplete")

    fg = doc["flow_graph"]
    _req(e, isinstance(fg, dict) and fg.get("lane") == mode, "flow_graph.lane must equal mode")
    _req(e, fg.get("nodes") == nodes, "flow_graph.nodes must be the fixed node ids for the mode")
    edges = fg.get("edges") or []
    _req(e, bool(edges) and all(isinstance(x, list) and len(x) == 2 and x[0] in nodes and x[1] in nodes
                                for x in edges), "flow_graph.edges must be non-empty node pairs")

    turns = doc["turns"]
    _req(e, isinstance(turns, list) and turns, "turns must be a non-empty list")
    for t in turns or []:
        for k in ("turn_index", "session", "kind", "text_safe", "path", "outcomes"):
            _req(e, k in t, f"turn missing {k!r}")
        _req(e, all(n in nodes for n in t.get("path", [])), f"turn {t.get('turn_index')} path has unknown node")
        _req(e, isinstance(t.get("outcomes", []), list), "turn outcomes must be a list")

    pipe = doc["pipeline"]
    _req(e, isinstance(pipe, list) and pipe, "pipeline must be a non-empty list")
    for p in pipe or []:
        missing = [k for k in PIPELINE_KEYS if k not in p]
        _req(e, not missing, f"pipeline entry missing {missing}")
        _req(e, p.get("node") in nodes, f"pipeline node {p.get('node')!r} not in flow_graph")
        _req(e, p.get("source") == ("event" if mode == "ltm" else "harness_observation"),
             "pipeline source must be 'event' (ltm) or 'harness_observation' (baseline)")

    ms = doc["memory_state"]
    _req(e, isinstance(ms, list), "memory_state must be a list")
    if mode == "baseline":
        _req(e, ms == [], "baseline memory_state must be []")
        _req(e, doc["retrieval"] == [], "baseline retrieval must be []")
        _req(e, isinstance(doc["baseline_observations"], list) and doc["baseline_observations"],
             "baseline_observations must be populated in baseline mode")
    else:
        _req(e, bool(ms), "ltm memory_state must be populated")
        for snap in ms:
            for k in ("after_turn", "memories", "deleted", "edges", "tombstones"):
                _req(e, k in snap, f"memory_state snapshot missing {k!r}")
            for m in snap.get("memories", []):
                _req(e, all(k in m for k in MEMORY_KEYS), "memory missing required fields")
            for ed in snap.get("edges", []):
                _req(e, ed.get("kind") in ("superseded_by", "contests"), "unknown edge kind")
            for tb in snap.get("tombstones", []):
                _req(e, "value_hmac" not in tb, "tombstones must not expose value_hmac")
        _req(e, isinstance(doc["retrieval"], list) and doc["retrieval"], "ltm retrieval must be populated")
        for r in doc["retrieval"]:
            missing = [k for k in RETRIEVAL_KEYS if k not in r]
            _req(e, not missing, f"retrieval entry missing {missing}")
            for c in r.get("candidates", []):
                _req(e, all(k in c for k in CANDIDATE_KEYS), "retrieval candidate missing score fields")
        _req(e, doc["baseline_observations"] == [], "ltm baseline_observations must be []")

    _req(e, isinstance(doc["retrieved"], list), "retrieved must be a list")
    _req(e, isinstance(doc["model_context"], dict), "model_context must be an object")
    for p in doc["probes"]:
        _req(e, p.get("probe") in PROBES and "turn_index" in p and isinstance(p.get("model_context"), dict),
             "probe entries need probe/turn_index/model_context")

    cs = doc["canary_scan"]
    _req(e, isinstance(cs, dict) and isinstance(cs.get("canaries"), list) and isinstance(cs.get("sinks"), list),
         "canary_scan needs canaries[] and sinks[]")
    for c in cs.get("canaries", []):
        _req(e, bool(CANARY_LABEL.match(c)), "canary entries must be LABEL:name labels, never values")
    for s in cs.get("sinks", []):
        _req(e, isinstance(s, dict) and "sink" in s and isinstance(s.get("hits"), int), "canary sink needs sink+hits")

    asserts = doc["assertions"]
    _req(e, isinstance(asserts, list) and asserts, "assertions must be non-empty")
    ids = [a.get("id") for a in asserts]
    _req(e, len(ids) == len(set(ids)), "assertion ids must be unique")
    for a in asserts:
        _req(e, isinstance(a.get("id"), str) and isinstance(a.get("name"), str) and isinstance(a.get("passed"), bool),
             "assertion needs id, name, passed(bool)")
    return e


def validate_file(path: Path) -> List[str]:
    return validate_trace(json.loads(Path(path).read_text(encoding="utf-8")))


if __name__ == "__main__":  # python contract.py results/ltm_demo/*.json
    bad = 0
    for arg in sys.argv[1:]:
        if arg.endswith("index.json"):
            continue
        problems = validate_file(Path(arg))
        print(("OK   " if not problems else "FAIL ") + arg + ("" if not problems else ": " + "; ".join(problems)))
        bad += bool(problems)
    sys.exit(1 if bad else 0)
