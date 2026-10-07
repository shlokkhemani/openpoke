"""Consolidation (deep dive §11, §12): INSERT / MERGE / SUPERSEDE / CONTEST / DROP_STALE.

Every function here runs inside the fenced ``BEGIN IMMEDIATE`` transaction opened by ``commit_candidate`` (§22).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from . import vocab
from .models import ConsolidationOutcome as CO
from .models import MemoryScope, NewRecord, Outcome, to_iso, utcnow
from .policy import on_merge, r2
from .store import MemoryStore

SUPERSEDE_MIN_CONF = 0.80  # only explicit statements supersede
TRUST_MARGIN = 0.10  # new may be slightly less confident than old (e.g. 0.90 vs 0.98 after reinforcement)
JACCARD_SAME, JACCARD_RELATED = 0.80, 0.50


class RetryConsolidate(Exception):
    """Optimistic version check failed: re-read and re-decide."""


def _one(conn: sqlite3.Connection, sql: str, params: Tuple[Any, ...]) -> Optional[Dict[str, Any]]:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _display(rec_or_row: Any) -> Optional[str]:
    if isinstance(rec_or_row, NewRecord):
        return vocab.display_value(rec_or_row.slot.predicate, rec_or_row.value_json)
    return vocab.display_value(rec_or_row["predicate"], rec_or_row["value_json"])


def keywords_for_row(slot_key: str, predicate: str, subject: str) -> str:
    entity = [p.split(":", 1)[1].replace("-", " ") for p in slot_key.split("|") if ":" in p and not p.startswith("pref.custom")]
    if subject != "user":
        entity.append(subject.split(":", 1)[-1].replace("-", " "))
    return " ".join(vocab.keywords_for(predicate) + entity)


# ---------------------------------------------------------------------------
# Similarity (§11), custom predicates only
# ---------------------------------------------------------------------------


def _stem_set(text: str) -> set:
    return set(vocab.stems(text or ""))


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def similar_custom(conn: sqlite3.Connection, scope: MemoryScope, memory_type: str, cand_text: str) -> Tuple[Optional[Dict[str, Any]], float]:
    terms = sorted(_stem_set(cand_text))
    if not terms:
        return None, 0.0
    q = " OR ".join(f'"{t}"' for t in terms)
    rows = conn.execute(
        "SELECT m.* FROM memories_fts f JOIN memories m ON m.id = f.memory_id WHERE memories_fts MATCH ?"
        " AND m.user_id=? AND f.user_id=? AND m.status='active' AND m.memory_type=? LIMIT 10",
        (q, scope.user_id, scope.user_id, memory_type),
    ).fetchall()
    best, best_j = None, 0.0
    cand = _stem_set(cand_text)
    for r in rows:
        j = jaccard(cand, _stem_set(r["canonical_text"]))
        if j > best_j:
            best, best_j = dict(r), j
    return best, best_j


# ---------------------------------------------------------------------------
# Outcomes (§12)
# ---------------------------------------------------------------------------


def insert(store: MemoryStore, conn: sqlite3.Connection, scope: MemoryScope, rec: NewRecord, reason: str) -> Outcome:
    new_id = store.insert_row(conn, scope, rec, status="active")
    return Outcome(CO.INSERT, memory_id=new_id, reason_codes=[reason],
                   detail={"slot_key": rec.slot_key, "new_id": new_id},
                   dev_detail={"display": _display(rec),
                               "reason": f"slot {rec.slot_key}: new value {_display(rec)}"})


def merge(conn: sqlite3.Connection, cur: Dict[str, Any], rec: NewRecord) -> Outcome:
    now = to_iso(utcnow())
    exp = cur["expires_at"]
    if exp and rec.expires_at:
        exp = max(exp, rec.expires_at)  # extend_ttl: sliding window
    n = conn.execute(
        "UPDATE memories SET reinforcement_count=reinforcement_count+1, confidence=?, "
        "last_confirmed_at=max(last_confirmed_at, ?), expires_at=?, version=version+1, updated_at=? "
        "WHERE id=? AND version=?",
        (on_merge(cur["confidence"], rec.confidence), rec.observed_at, exp, now, cur["id"], cur["version"]),
    ).rowcount
    if n == 0:
        raise RetryConsolidate()
    return Outcome(CO.MERGE, memory_id=cur["id"], reason_codes=["SAME_SLOT_SAME_VALUE"],
                   detail={"slot_key": rec.slot_key, "reinforcement_count": cur["reinforcement_count"] + 1},
                   dev_detail={"display": _display(rec), "reason": f"slot {rec.slot_key}: restated {_display(rec)}"})


def supersede(store: MemoryStore, conn: sqlite3.Connection, scope: MemoryScope, old: Dict[str, Any], rec: NewRecord) -> Outcome:
    now = to_iso(utcnow())
    # Order is forced by ux_one_active_single_slot: demote the old row BEFORE inserting the new active one.
    n = conn.execute(
        "UPDATE memories SET status='superseded', superseded_at=?, version=version+1, updated_at=? "
        "WHERE id=? AND version=?",
        (now, now, old["id"], old["version"]),
    ).rowcount
    if n == 0:
        raise RetryConsolidate()
    store.unindex_row(conn, scope, old["id"])
    new_id = store.insert_row(conn, scope, rec, status="active", supersedes_id=old["id"])
    conn.execute("UPDATE memories SET superseded_by_id=? WHERE id=?", (new_id, old["id"]))
    resolved: List[str] = []
    for sib in conn.execute("SELECT id FROM memories WHERE user_id=? AND slot_key=? AND status='contested'",
                            (scope.user_id, old["slot_key"])).fetchall():
        conn.execute("UPDATE memories SET status='superseded', superseded_by_id=?, superseded_at=?, "
                     "version=version+1, updated_at=? WHERE id=?", (new_id, now, now, sib["id"]))
        store.unindex_row(conn, scope, sib["id"])
        resolved.append(sib["id"])
    old_disp, new_disp = _display(old), _display(rec)
    return Outcome(
        CO.SUPERSEDE, memory_id=new_id, old_id=old["id"],
        reason_codes=["SAME_SLOT_DIFFERENT_VALUE", "NEWER_EXPLICIT"],
        detail={"slot_key": rec.slot_key, "old_id": old["id"], "new_id": new_id,
                "refs": {"old_id": old["id"], "resolved_contested": resolved},
                "scores": {"importance": rec.importance, "confidence": rec.confidence}},
        dev_detail={"display": new_disp,
                    "reason": f"slot {rec.slot_key}: {new_disp} replaces {old_disp} "
                              f"({rec.confidence:.2f} ≥ {SUPERSEDE_MIN_CONF:.2f})"},
    )


def contest(store: MemoryStore, conn: sqlite3.Connection, scope: MemoryScope, cur: Dict[str, Any], rec: NewRecord) -> Outcome:
    new_id = store.insert_row(conn, scope, rec, status="contested", contests_id=cur["id"])
    return Outcome(CO.CONTEST, memory_id=new_id, old_id=cur["id"],
                   reason_codes=["SAME_SLOT_DIFFERENT_VALUE", "LOWER_CONFIDENCE"],
                   detail={"slot_key": rec.slot_key, "new_id": new_id, "refs": {"contests_id": cur["id"]},
                           "scores": {"confidence": rec.confidence, "active_confidence": cur["confidence"]}},
                   dev_detail={"display": _display(rec),
                               "reason": f"slot {rec.slot_key}: {_display(rec)} contests {_display(cur)} "
                                         f"({rec.confidence:.2f} < {SUPERSEDE_MIN_CONF:.2f})"})


def consolidate(store: MemoryStore, conn: sqlite3.Connection, scope: MemoryScope, rec: NewRecord) -> Outcome:
    cur = _one(conn,
               "SELECT * FROM memories WHERE user_id=? AND slot_key=? AND status='active' "
               "AND (cardinality='single' OR value_hmac=?)",
               (scope.user_id, rec.slot_key, rec.value_hmac))

    if rec.slot.cardinality == "multi":
        if cur:
            return merge(conn, cur, rec)
        if rec.slot.predicate.startswith("pref.custom:"):
            twin, j = similar_custom(conn, scope, rec.slot.memory_type, rec.canonical_text)
            if twin and j >= JACCARD_SAME:
                return merge(conn, twin, rec)
            if twin and j >= JACCARD_RELATED:
                rec.related_id = twin["id"]
        return insert(store, conn, scope, rec, "NEW_VALUE")

    if cur is None:
        return insert(store, conn, scope, rec, "NEW_SLOT")
    if rec.observed_at <= cur["observed_at"] and rec.value_hmac != cur["value_hmac"]:
        return Outcome(CO.DROP_STALE, memory_id=cur["id"], reason_codes=["OLDER_STATEMENT"],
                       detail={"slot_key": rec.slot_key, "refs": {"active_id": cur["id"]},
                               "job_observed_at": rec.observed_at, "active_observed_at": cur["observed_at"]},
                       dev_detail={"display": _display(rec),
                                   "reason": f"slot {rec.slot_key}: {_display(rec)} is older than active "
                                             f"{_display(cur)}"})
    if rec.value_hmac == cur["value_hmac"]:
        return merge(conn, cur, rec)
    if rec.confidence >= SUPERSEDE_MIN_CONF and rec.confidence >= r2(cur["confidence"] - TRUST_MARGIN):
        return supersede(store, conn, scope, cur, rec)
    return contest(store, conn, scope, cur, rec)
