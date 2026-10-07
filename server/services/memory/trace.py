"""Trace assembler (deep dive §24.1, design §25). Pure reader: never writes.

Turns the event rows of one turn into the ``turns[i]`` / ``pipeline[]`` / ``retrieval`` slices of
``openpoke.ltm.demo_trace.v1`` and snapshots sanitised memory state. Every returned document passes the leak guard.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .events import EventSink
from .models import MemoryScope
from .privacy import prohibited_findings
from .store import MemoryStore

LTM_NODES = ("conversation", "ingress_scrub", "privacy", "extract", "policy", "consolidate", "store", "ignore",
             "reject", "supersede", "delete", "fence_drop", "retrieve", "agent")
BASELINE_NODES = ("conversation", "raw_persistence", "working_memory", "broad_context", "agent")
LTM_EDGES = [["conversation", "ingress_scrub"], ["ingress_scrub", "privacy"], ["privacy", "extract"],
             ["extract", "policy"], ["policy", "consolidate"], ["policy", "ignore"], ["policy", "reject"],
             ["consolidate", "store"], ["consolidate", "supersede"], ["consolidate", "fence_drop"],
             ["store", "retrieve"], ["retrieve", "agent"], ["conversation", "delete"]]
BASELINE_EDGES = [["conversation", "raw_persistence"], ["raw_persistence", "working_memory"],
                  ["working_memory", "broad_context"], ["broad_context", "agent"]]

# Deep dive §24.1, extended to every stage in the design §17 enum so each pipeline entry has a node.
STAGE_TO_NODE = {"ingest": "conversation", "ingress.scrub": "ingress_scrub", "privacy.scrub": "privacy",
                 "privacy.classify": "privacy", "privacy.egress": "retrieve", "extract": "extract",
                 "extract.clause": "extract", "validate": "extract", "policy": "policy",
                 "consolidate": "consolidate", "store": "store", "index": "store", "fence_drop": "fence_drop",
                 "forget.detect": "delete", "forget.apply": "delete", "retrieve.query": "retrieve",
                 "retrieve.filter": "retrieve", "retrieve.candidates": "retrieve", "retrieve.rank": "retrieve",
                 "retrieve.select": "retrieve", "prompt.render": "agent", "expire": "store", "purge": "store"}
# Decision -> outcome node(s). SUPERSEDE lands a new active row, so it passes through "store" as well.
OUTCOME_NODES = {"IGNORE": ["ignore"], "NO_CANDIDATE": ["ignore"], "REJECT": ["reject"], "QUARANTINE": ["reject"],
                 "INSERT": ["store"], "MERGE": ["store"], "SUPERSEDE": ["supersede", "store"], "CONTEST": ["store"],
                 "TOMBSTONED": ["fence_drop"], "EPOCH_CHANGED": ["fence_drop"], "DELETE": ["delete"]}
# Stages whose decision is diagnostic only (no outcome node on the path).
_NO_OUTCOME_STAGES = {"retrieve.rank", "retrieve.filter", "privacy.egress", "ingress.scrub", "extract"}
_INPUT_STAGES = {"extract.clause", "validate", "privacy.classify", "policy"}
_OUTPUT_STAGES = {"consolidate", "retrieve.rank", "retrieve.filter", "retrieve.select", "prompt.render"}


class LeakError(AssertionError):
    """A prohibited-class pattern reached a trace document."""


def leak_guard(doc: Any) -> Any:
    """``ingress_scrub(json.dumps(doc))`` must be a no-op. Raises with detector kinds only (never the value)."""
    blob = json.dumps(doc, sort_keys=True, ensure_ascii=False, default=str)
    hits = prohibited_findings(blob)
    if hits:
        raise LeakError("prohibited pattern in trace: " + ",".join(sorted({h.kind for h in hits})))
    return doc


def _outcome_nodes(e: Dict[str, Any]) -> List[str]:
    if e["stage"] in _NO_OUTCOME_STAGES:
        return []
    if e["stage"] == "forget.apply" and e["decision"] != "DELETE":
        return []
    return OUTCOME_NODES.get(e["decision"] or "", [])


def _node(e: Dict[str, Any]) -> str:
    nodes = _outcome_nodes(e)
    return nodes[0] if nodes else STAGE_TO_NODE[e["stage"]]


def _reason(e: Dict[str, Any]) -> Optional[str]:
    d = e["detail"]
    if d.get("reason"):
        return str(d["reason"])
    if e["reason_codes"]:
        return ", ".join(e["reason_codes"])
    return None


def pipeline_entry(e: Dict[str, Any], seq: int) -> Dict[str, Any]:
    d = e["detail"]
    scores = d.get("scores")
    if scores is None and any(k in d for k in ("rel", "importance", "confidence")):
        scores = {k: d[k] for k in ("rel", "imp", "conf", "rec", "total", "importance", "confidence") if k in d}
    return {
        "trace_id": e["trace_id"],
        "seq": seq,
        "stage": e["stage"],
        "node": _node(e),
        "candidate_id": e["candidate_id"],
        "memory_id": e["memory_id"],
        "input_safe": e["safe_text"] if e["stage"] in _INPUT_STAGES else None,
        "output_safe": e["safe_text"] if e["stage"] in _OUTPUT_STAGES else None,
        "decision": e["decision"],
        "reason_codes": e["reason_codes"],
        "reason": _reason(e),
        "scores": scores,
        "refs": d.get("refs", {}),
        "detail": {k: v for k, v in d.items() if k not in ("refs", "scores", "reason")},
        "ts": e["ts"],
        "source": "event",
    }


def _short_label(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.strip().rstrip(".!?")
    t = re.sub(r"^(?:actually,?\s+)?(?:i'?m|i am|i)\s+", "", t, flags=re.I)
    return t[:80]


def summarise_outcomes(ev: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One outcome per clause / candidate / forget / fence drop, in event order."""
    by_cand: Dict[str, Dict[str, Any]] = {}
    out: List[Dict[str, Any]] = []
    in_duplicate = False
    for e in ev:
        d = e["detail"]
        if e["stage"] == "extract":
            in_duplicate = bool(d.get("duplicate"))
        if e["stage"] == "extract.clause":
            if e["decision"] == "NO_CANDIDATE":
                reason = (e["reason_codes"] or [None])[0]
                out.append({"label": _short_label(e["safe_text"]) or f"clause {d.get('clause_index')}",
                            "clause_index": d.get("clause_index"), "decision": "IGNORE", "result": "NO_CANDIDATE",
                            "reason": reason, "candidate_id": None, "memory_id": None})
            else:
                item = {"label": d.get("label") or _short_label(e["safe_text"]), "clause_index": d.get("clause_index"),
                        "candidate_id": e["candidate_id"], "decision": None, "result": None, "reason": None,
                        "memory_id": None, "duplicate": in_duplicate}
                by_cand[e["candidate_id"]] = item
                out.append(item)
        elif e["stage"] in ("validate", "policy") and e["candidate_id"]:
            item = by_cand.get(e["candidate_id"])
            if item is None:
                item = {"label": d.get("label"), "candidate_id": e["candidate_id"], "decision": None,
                        "result": None, "reason": None, "memory_id": None}
                by_cand[e["candidate_id"]] = item
                out.append(item)
            if d.get("label_value") or d.get("label"):
                item["label"] = d.get("label_value") or d["label"]
            if d.get("duplicate") or item.get("duplicate"):
                item["duplicate"] = True
            item["decision"] = e["decision"]
            if e["decision"] != "STORE":
                item["result"] = e["decision"]
                item["reason"] = ", ".join(e["reason_codes"]) or None
            if e["stage"] == "policy" and "importance" in d:
                item["importance"] = d["importance"]
        elif e["stage"] == "consolidate" and e["candidate_id"] in by_cand:
            item = by_cand[e["candidate_id"]]
            item["result"] = e["decision"]
            item["memory_id"] = e["memory_id"]
            if d.get("refs", {}).get("old_id"):
                item["supersedes"] = d["refs"]["old_id"]
            item["reason"] = _reason(e)
        elif e["stage"] == "fence_drop":
            item = by_cand.get(e["candidate_id"] or "")
            if item is None or item.get("result") is not None:
                item = {"label": (item or {}).get("label") or d.get("label"), "candidate_id": e["candidate_id"],
                        "decision": "STORE", "memory_id": None}
                out.append(item)
            item.update({"result": "FENCE_DROP", "reason": e["decision"], "refs": d.get("refs", {}),
                         "duplicate": bool(d.get("duplicate"))})
        elif e["stage"] == "forget.apply":
            out.append({"label": d.get("label") or "forget request", "decision": "DELETE",
                        "result": e["decision"] if e["decision"] != "DELETE" else
                        ("TOMBSTONE" if not d.get("memory_ids") else "DELETE"),
                        "reason": _reason(e), "memory_ids": d.get("memory_ids", []), "slot_key": d.get("slot_key")})
    return out


def assemble_retrieval(ev: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    q = next((e for e in ev if e["stage"] == "retrieve.query"), None)
    if q is None:
        return None
    qd = q["detail"]
    sel = next((e for e in ev if e["stage"] == "retrieve.select"), None)
    cands = []
    for e in ev:
        if e["stage"] != "retrieve.rank":
            continue
        d = e["detail"]
        cands.append({"memory_id": e["memory_id"], "display": d.get("display"), "generators": d.get("generators", []),
                      "rel": d.get("rel"), "imp": d.get("imp"), "conf": d.get("conf"), "rec": d.get("rec"),
                      "total": d.get("total"), "selected": e["decision"] == "SELECTED",
                      "drop_reason": d.get("drop")})
    return {
        "trace_id": q["trace_id"],
        "query": {"terms": qd.get("terms", []), "families": qd.get("families", []),
                  "entities": qd.get("entities", []), "n_terms": qd.get("n_terms")},
        "hard_filters": qd.get("hard_filters", {}),
        "excluded_by_filters": [{"memory_id": e["memory_id"], "display": e["detail"].get("display"),
                                 "filter": e["detail"].get("filter")}
                                for e in ev if e["stage"] == "retrieve.filter"],
        "candidates": cands,
        "selected": (sel["detail"].get("selected", []) if sel else []),
        "ltm_block": (sel["safe_text"] or "") if sel else "",
        "ltm_block_tokens": (sel["detail"].get("tokens", 0) if sel else 0),
        "egress": next(({"decision": e["decision"], **e["detail"]} for e in ev if e["stage"] == "privacy.egress"), None),
    }


def assemble_turn_trace(sink: EventSink, scope: MemoryScope, trace_id: str) -> Dict[str, Any]:
    ev = sink.events(scope, trace_id)
    ingest = next((e for e in ev if e["stage"] == "ingest"), None)
    kind = ingest["detail"].get("kind") if ingest else None
    path: List[str] = ["conversation"]
    for e in ev:
        for n in [STAGE_TO_NODE.get(e["stage"])] + _outcome_nodes(e):
            if n and n not in path:
                path.append(n)
    if (any(e["stage"] == "prompt.render" for e in ev) or kind == "probe") and "agent" not in path:
        path.append("agent")
    doc = {
        "trace_id": trace_id,
        "turn_id": ingest["detail"].get("turn_id") if ingest else None,
        "source_kind": ingest["detail"].get("source_kind") if ingest else None,
        "kind": kind,
        "path": path,
        "pipeline": [pipeline_entry(e, i) for i, e in enumerate(ev)],
        "outcomes": summarise_outcomes(ev),
        "retrieval": assemble_retrieval(ev),
    }
    return leak_guard(doc)


def _display(row: Dict[str, Any]) -> Optional[str]:
    from .vocab import display_value  # local import: vocab is optional for the skeleton

    return display_value(row["predicate"], row.get("value_json"))


def status_history(sink: EventSink, scope: MemoryScope, memory_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    hist: Dict[str, List[Dict[str, Any]]] = {m: [] for m in memory_ids}

    def add(mem_id: Optional[str], status: str, e: Dict[str, Any]) -> None:
        if mem_id in hist:
            hist[mem_id].append({"status": status, "trace_id": e["trace_id"], "ts": e["ts"]})

    for e in sink.events_for_memory(scope, memory_ids):
        d = e["detail"]
        if e["stage"] == "consolidate":
            if e["decision"] in ("INSERT", "SUPERSEDE"):
                add(e["memory_id"], "active", e)
            elif e["decision"] == "CONTEST":
                add(e["memory_id"], "contested", e)
            if e["decision"] == "SUPERSEDE":
                add(d.get("refs", {}).get("old_id"), "superseded", e)
                for sib in d.get("refs", {}).get("resolved_contested", []):
                    add(sib, "superseded", e)
        elif e["stage"] == "forget.apply" and e["decision"] == "DELETE":
            for mem_id in d.get("memory_ids", []):
                add(mem_id, "deleted", e)
        elif e["stage"] == "expire":
            add(e["memory_id"], "expired", e)
    return hist


def memory_state_snapshot(store: MemoryStore, sink: EventSink, scope: MemoryScope) -> Dict[str, Any]:
    """Sanitised state (design §17.1): MEMORY_SAFE fields, status edges, tombstones without ``value_hmac``."""
    rows = store.all_rows(scope)
    hist = status_history(sink, scope, [r["id"] for r in rows])
    memories = []
    for r in rows:
        deleted = r["status"] == "deleted"
        memories.append({
            "id": r["id"], "slot_key": r["slot_key"], "memory_type": r["memory_type"], "status": r["status"],
            "display": None if deleted else _display(r),
            "canonical_text": r["canonical_text"], "importance": r["importance"], "confidence": r["confidence"],
            "supersedes_id": r["supersedes_id"], "superseded_by_id": r["superseded_by_id"],
            "contests_id": r["contests_id"], "observed_at": r["observed_at"], "expires_at": r["expires_at"],
            "deleted_at": r["deleted_at"], "status_history": hist.get(r["id"], []),
        })
    doc = {
        "memories": memories,
        "deleted": [{"id": r["id"], "slot_key": r["slot_key"], "deleted_at": r["deleted_at"]}
                    for r in rows if r["status"] == "deleted"],
        "edges": [{"from": r["id"], "to": r["superseded_by_id"], "kind": "superseded_by"}
                  for r in rows if r["superseded_by_id"]]
                 + [{"from": r["id"], "to": r["contests_id"], "kind": "contests"} for r in rows if r["contests_id"]],
        "tombstones": [{"slot_key": t["slot_key"], "scope": t["scope"], "deleted_at": t["deleted_at"],
                        "reason": t["reason"]} for t in store.tombstones(scope)],
    }
    return leak_guard(doc)
