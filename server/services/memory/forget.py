"""Forgetting (deep dive §21, design §14): synchronous detect + resolve + purge, empty-slot tombstones (D27)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import vocab
from .events import EventSink
from .models import MemoryScope, to_iso, utcnow
from .retrieval import Cand, Filters, Query, build_query, candidates, relevance
from .store import MemoryStore

FORGET_VERB = r"\b(forget|erase|stop remembering|don'?t remember|unlearn)\b"
DELETE_VERB = r"\b(delete|remove|wipe|clear)\b"
MEMORY_CUE = r"\b(remember|memory|memories|know about me|you know|preference|that i (said|told)|about me)\b"
NEG_FORGET = r"\b(don'?t|do not|never|won'?t)\s+forget\b"  # "don't forget to email Bob" is a reminder, not a forget
ALL_RX = r"\b(everything|all of it|all memories)\b"

RESOLVE_MIN_REL, RESOLVE_MARGIN = 0.50, 0.15


@dataclass
class ForgetRequest:
    kind: str  # 'targeted' | 'all'
    phrase: str
    clause_indices: List[int] = field(default_factory=list)


@dataclass
class ForgetResult:
    notice: str
    decision: str  # DELETE | AMBIGUOUS | NO_MATCH | CONFIRM_ALL
    slot_key: Optional[str] = None
    memory_ids: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)
    tombstone_at: Optional[str] = None


# LTM_BLOCKERS.md B3: the verbatim §21 grammar fires on any "forget" (e.g. "I forget what time my meeting is").
# A clause is a forget request only when it is addressed to the assistant (not "I [adverb] forget/forgot ...") AND
# names a memory target (a memory cue, or a possessive / "what I said" / "everything" object).
SELF_FORGET = (r"\b(?:i|we)\s+(?:(?!you\b)[\w']+\s+){0,2}?"
               r"(?:forget|forgot|forgets|don'?t remember|do not remember|can'?t remember|cannot remember)\b")
TARGET_RX = (r"^(?:about\s+)?(?:my|mine|our|everything|all\b|what\s+(?:i|you)\s+(?:said|told|know|remember)|"
             r"what\s+you\s+know|the\s+fact\s+that|that\s+i\s+(?:said|told|prefer|like))\b")


def text_after_verb(text: str) -> str:
    m = re.search(FORGET_VERB, text, re.I) or re.search(DELETE_VERB, text, re.I)
    return text[m.end():].strip() if m else text


def _clause_request(clause: str) -> Optional[ForgetRequest]:
    if re.search(NEG_FORGET, clause, re.I) or re.search(SELF_FORGET, clause, re.I):
        return None
    has_forget = re.search(FORGET_VERB, clause, re.I)
    has_delete = re.search(DELETE_VERB, clause, re.I)
    if not (has_forget or has_delete):
        return None
    obj = text_after_verb(clause)
    cue = re.search(MEMORY_CUE, clause, re.I)
    if has_delete and not has_forget and not cue:
        return None  # "Delete the email from Bob" is not about memory
    if not cue and not re.search(TARGET_RX, obj, re.I):
        return None  # "forget it", "forget the Dana thing" name no memory target
    if re.search(ALL_RX, obj, re.I):
        return ForgetRequest(kind="all", phrase=obj)
    return ForgetRequest(kind="targeted", phrase=obj)


def detect(text: str) -> Optional[ForgetRequest]:
    """Per clause (B3). Returns the first forget clause's request; ``clause_indices`` lists every forget clause so the
    rest of the message can still be ingested as ordinary facts."""
    from .extractor import split_clauses

    found: Optional[ForgetRequest] = None
    indices: List[int] = []
    for i, clause in enumerate(split_clauses(text)):
        fr = _clause_request(clause)
        if fr:
            indices.append(i)
            found = found or fr
    if found:
        found.clause_indices = indices
    return found


def _best_per_slot(cands: Dict[str, Cand], q: Query) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for c in cands.values():
        rel = relevance(c, q)
        cur = best.get(c.row["slot_key"])
        if cur is None or rel > cur["rel"]:
            best[c.row["slot_key"]] = {"slot_key": c.row["slot_key"], "predicate": c.row["predicate"], "rel": rel}
    return sorted(best.values(), key=lambda b: (-b["rel"], b["slot_key"]))


def apply(store: MemoryStore, sink: EventSink, scope: MemoryScope, fr: ForgetRequest, trace_id: str) -> ForgetResult:
    emit = lambda *a, **k: sink.emit(scope, trace_id, *a, **k)  # noqa: E731
    if fr.kind == "all":  # prototype: API-only for safety; chat gets a notice
        res = ForgetResult("The user asked to forget everything. Confirm with them and point them to memory settings; "
                           "nothing was deleted yet.", "CONFIRM_ALL")
        emit("forget.apply", decision="CONFIRM_ALL", detail={"label": "forget everything"})
        return res
    q = build_query(fr.phrase)
    with store.read() as conn:
        cands, _ = candidates(conn, scope, q, Filters(statuses=("active", "contested", "superseded"),
                                                      sensitivity=("low", "medium", "high")), to_iso(utcnow()))
    by_slot = _best_per_slot(cands, q)
    top2 = [round(b["rel"], 2) for b in by_slot[:2]]
    if not by_slot or by_slot[0]["rel"] < RESOLVE_MIN_REL:
        # Forget-before-write (D27): the memory may not exist YET (its ingest job is still in flight).
        fams = q.families
        if len(fams) == 1 and not vocab.spec_for(fams[0]).keyed:
            slot_key = f"user|{fams[0]}"
            out = store.purge_slot(scope, slot_key, reason="user_forget")  # no rows: slot tombstone only
            lbl = vocab.label(fams[0])
            emit("forget.apply", decision="DELETE", detail={
                "slot_key": slot_key, "count": len(out["deleted_ids"]), "memory_ids": out["deleted_ids"],
                "tombstone_at": out["deleted_at"], "tombstone_only": True, "top_rel": top2,
                "label": f"forget {lbl}"})
            return ForgetResult(f"No stored memory about {lbl} yet; it will not be remembered.", "DELETE",
                                slot_key, out["deleted_ids"], tombstone_at=out["deleted_at"])
        emit("forget.apply", decision="NO_MATCH", detail={"top_rel": top2, "families": fams, "label": "forget request"})
        return ForgetResult("The user asked to forget something, but no matching long-term memory was found.", "NO_MATCH")
    if len(by_slot) > 1 and by_slot[1]["rel"] > by_slot[0]["rel"] - RESOLVE_MARGIN:
        labels = ", ".join(vocab.label(b["predicate"]) for b in by_slot[:3])
        emit("forget.apply", decision="AMBIGUOUS",
             detail={"top_rel": top2, "slot_keys": [b["slot_key"] for b in by_slot[:3]], "label": "forget request"})
        return ForgetResult(f"Ambiguous forget request. Ask which one: {labels}. Nothing was deleted yet.", "AMBIGUOUS")
    target = by_slot[0]
    out = store.purge_slot(scope, target["slot_key"], reason="user_forget")
    lbl = vocab.label(target["predicate"])
    emit("forget.apply", decision="DELETE", detail={
        "slot_key": target["slot_key"], "count": len(out["deleted_ids"]), "memory_ids": out["deleted_ids"],
        "tombstone_at": out["deleted_at"], "tombstone_only": False, "top_rel": top2, "label": f"forget {lbl}"})
    return ForgetResult(f"Deleted {len(out['deleted_ids'])} long-term memory item(s) about: {lbl}.", "DELETE",
                        target["slot_key"], out["deleted_ids"], tombstone_at=out["deleted_at"])


def forget_all(store: MemoryStore, sink: EventSink, scope: MemoryScope, trace_id: str = "api") -> Dict[str, Any]:
    out = store.forget_all(scope)
    sink.emit(scope, trace_id, "forget.apply", decision="DELETE",
              detail={"slot_key": None, "count": len(out["deleted_ids"]), "memory_ids": out["deleted_ids"],
                      "tombstone_at": out["deleted_at"], "label": "forget everything"})
    return out
