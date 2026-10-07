"""Retrieval (deep dive §14, §16-§18): hard filters in SQL, three candidate generators, ranking, top-k, P2 egress.

No LLM on the read path. Superseded / expired / deleted rows are never candidates; the debug-only
``retrieve.filter`` view lists them with the filter that excluded them (§24.1).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import privacy, vocab
from .events import EventSink
from .models import MemoryScope, from_iso, to_iso, utcnow
from .policy import effective_confidence, r2
from .render import Item, approx_tokens, render_block, render_item
from .store import MemoryStore

W_REL, W_IMP, W_CONF, W_REC = 0.55, 0.20, 0.15, 0.10
B0 = 5.0  # |bm25| at which lexical strength saturates
REL_FLOOR, SCORE_FLOOR = 0.25, 0.45
K_MAX, TOKEN_BUDGET, CONSTRAINT_RESERVE = 8, 400, 3
REC_HALF_LIFE = {"project": 30}
REC_DEFAULT_HL = 180
FTS_LIMIT = 50
ALL_STATUSES = ("active", "contested", "superseded", "expired", "quarantined")  # 'deleted' has no content


@dataclass
class Query:
    terms: List[str]  # stems, placeholders never included
    fts_terms: List[str]  # unstemmed content tokens (FTS5's porter tokenizer stems them itself)
    families: List[str]
    entities: List[str]
    categories: List[str]


@dataclass
class Filters:
    statuses: Tuple[str, ...] = ("active", "contested")
    not_expired: bool = True
    sensitivity: Tuple[str, ...] = ("low", "medium")
    types: Optional[Tuple[str, ...]] = None
    uses: str = "interaction_context"

    def as_dict(self, scope: MemoryScope) -> Dict[str, Any]:
        d: Dict[str, Any] = {"user_scope": scope.user_id, "statuses": list(self.statuses),
                             "not_expired": self.not_expired, "sensitivity": list(self.sensitivity),
                             "allowed_use": self.uses}
        if self.types:
            d["types"] = list(self.types)
        return d


@dataclass
class Cand:
    row: Dict[str, Any]
    slot_match: int = 0
    bm25: Optional[float] = None
    reserved: bool = False
    generators: List[str] = field(default_factory=list)
    contested_sibling: Optional[Dict[str, Any]] = None


@dataclass
class Scored:
    c: Cand
    rel: float
    imp: float
    conf: float
    rec: float
    score: float
    drop: Optional[str]


# ---------------------------------------------------------------------------
# Query (§16)
# ---------------------------------------------------------------------------



def categories_of_query(text: str) -> List[str]:
    return sorted(k for k, rx in privacy.LEXICON.items() if re.search(rx, text, re.I))


def build_query(llm_safe_text: str) -> Query:
    toks = vocab.content_tokens(llm_safe_text)
    terms: List[str] = []
    for t in toks:
        s = vocab.stem(t)
        if s not in terms:
            terms.append(s)
    families: List[str] = []
    for t in terms:
        for p in vocab.INTENT_LEXICON.get(t, []):
            if p not in families:
                families.append(p)
    entities: List[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", llm_safe_text or ""):
        for i, w in enumerate(vocab.raw_tokens(sentence)):
            if i == 0 or vocab.is_placeholder(w) or not re.fullmatch(r"[A-Z][a-z]+", w) or w == "I":
                continue
            e = vocab.normalise_entity(w)
            if e not in entities:
                entities.append(e)
    fts_terms = []
    for t in toks:
        if t not in fts_terms:
            fts_terms.append(t)
    return Query(terms, fts_terms, families, entities, categories_of_query(llm_safe_text or ""))


def allowed_filters(source_kind: str, q: Query, base: Optional[Filters] = None) -> Filters:
    f = base or Filters()
    if source_kind == "agent_message":  # attacker-influenceable query text (§18)
        f.types = ("constraint", "preference")
        f.sensitivity = ("low",)
    elif q.categories and base is None:
        f.sensitivity = ("low", "medium", "high")  # 'high' rows are then kept only when on topic
    return f


def fts_query_string(terms: Sequence[str]) -> str:
    # OR of quoted terms, so special characters can't inject FTS syntax
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in terms if t)


# ---------------------------------------------------------------------------
# Candidate generators (§16)
# ---------------------------------------------------------------------------


def _where(f: Filters, now_iso: str, alias: str = "m") -> Tuple[str, List[Any]]:
    sql = [f"{alias}.status IN ({','.join('?' * len(f.statuses))})"]
    params: List[Any] = list(f.statuses)
    if f.not_expired:
        sql.append(f"({alias}.expires_at IS NULL OR {alias}.expires_at > ?)")
        params.append(now_iso)
    sql.append(f"{alias}.sensitivity IN ({','.join('?' * len(f.sensitivity))})")
    params.extend(f.sensitivity)
    sql.append(f"instr({alias}.allowed_uses, ?) > 0")
    params.append(json.dumps(f.uses))
    if f.types:
        sql.append(f"{alias}.memory_type IN ({','.join('?' * len(f.types))})")
        params.extend(f.types)
    return " AND ".join(sql), params


def sql_by_predicates(conn: sqlite3.Connection, scope: MemoryScope, families: Sequence[str], f: Filters,
                      now_iso: str) -> List[Dict[str, Any]]:
    if not families:
        return []
    where, params = _where(f, now_iso)
    rows = conn.execute(
        f"SELECT m.* FROM memories m WHERE m.user_id=? AND m.predicate IN ({','.join('?' * len(families))}) AND {where}",
        [scope.user_id, *families, *params],
    ).fetchall()
    return [dict(r) for r in rows]


def fts(conn: sqlite3.Connection, scope: MemoryScope, q: Query, f: Filters, now_iso: str) -> List[Dict[str, Any]]:
    qs = fts_query_string(q.fts_terms)
    if not qs:
        return []
    where, params = _where(f, now_iso)
    try:
        rows = conn.execute(
            "SELECT m.*, bm25(memories_fts, 1.0, 0.6) AS bm FROM memories_fts f JOIN memories m ON m.id = f.memory_id"
            f" WHERE memories_fts MATCH ? AND m.user_id = ? AND f.user_id = ? AND {where} ORDER BY bm LIMIT {FTS_LIMIT}",
            [qs, scope.user_id, scope.user_id, *params],
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def sql_constraints(conn: sqlite3.Connection, scope: MemoryScope, q: Query, f: Filters,
                    now_iso: str) -> List[Dict[str, Any]]:
    if f.types and "constraint" not in f.types:
        return []
    where, params = _where(f, now_iso)
    rows = conn.execute(
        f"SELECT m.* FROM memories m WHERE m.user_id=? AND m.memory_type='constraint' AND {where}",
        [scope.user_id, *params],
    ).fetchall()
    out = []
    for r in rows:
        r = dict(r)
        if any(e in r["slot_key"].split("|") for e in q.entities) or r["predicate"] in q.families:
            out.append(r)
    return out


def _on_topic(row: Dict[str, Any], q: Query) -> bool:
    return row["sensitivity"] != "high" or bool(set(json.loads(row["pii_categories"] or "[]")) & set(q.categories))


def candidates(conn: sqlite3.Connection, scope: MemoryScope, q: Query, f: Filters, now_iso: str
               ) -> Tuple[Dict[str, Cand], Dict[str, int]]:
    out: Dict[str, Cand] = {}
    counts = {"slot": 0, "fts": 0, "constraint": 0}
    for m in sql_by_predicates(conn, scope, q.families, f, now_iso):  # slot route
        out[m["id"]] = Cand(m, slot_match=1, generators=["slot"])
        counts["slot"] += 1
    for m in fts(conn, scope, q, f, now_iso):  # lexical
        c = out.setdefault(m["id"], Cand(m, slot_match=0))
        c.bm25 = m.get("bm")
        c.generators.append("fts")
        counts["fts"] += 1
    for m in sql_constraints(conn, scope, q, f, now_iso):  # safety-relevant
        c = out.setdefault(m["id"], Cand(m, slot_match=1))
        c.slot_match = 1
        c.reserved = True
        c.generators.append("constraint")
        counts["constraint"] += 1
    for mid in [k for k, c in out.items() if not _on_topic(c.row, q)]:
        del out[mid]
    _attach_contested_siblings(conn, scope, out, q, f, now_iso)
    counts["total"] = len(out)
    return out, counts


def _attach_contested_siblings(conn: sqlite3.Connection, scope: MemoryScope, out: Dict[str, Cand], q: Query,
                               f: Filters, now_iso: str) -> None:
    """A contested row joins its active sibling as one item (rendered as an explicit conflict). The sibling must pass
    the SAME hard filters and on-topic check as any candidate (D9; review M5). If it does not, it is never rendered;
    the contested row, which passed the filters itself, stays a standalone candidate."""
    for mid in [k for k, c in out.items() if c.row["status"] == "contested"]:
        c = out[mid]
        active = next((a for a in out.values() if a.row["id"] == c.row["contests_id"]), None)
        if active is None:
            where, params = _where(f, now_iso)
            row = conn.execute(f"SELECT m.* FROM memories m WHERE m.id=? AND m.user_id=? AND m.status='active' AND {where}",
                               [c.row["contests_id"], scope.user_id, *params]).fetchone()
            if row is None or not _on_topic(dict(row), q):
                continue  # sibling not allowed in this context: keep the contested row on its own
            active = Cand(dict(row), slot_match=c.slot_match, bm25=c.bm25, generators=list(c.generators))
            out[active.row["id"]] = active
        del out[mid]
        active.contested_sibling = c.row


# ---------------------------------------------------------------------------
# Ranking and selection (§17)
# ---------------------------------------------------------------------------


def memory_terms(row: Dict[str, Any]) -> Set[str]:
    kw = vocab.keywords_for(row["predicate"])
    return set(vocab.stems(row["canonical_text"] or "")) | {vocab.stem(k) for k in kw}


def relevance(c: Cand, q: Query) -> float:
    qt = set(q.terms)
    coverage = len(qt & memory_terms(c.row)) / max(1, len(qt))
    lexical = 0.5 * coverage + 0.5 * min(1.0, abs(c.bm25 or 0) / B0)
    return max(0.9 * c.slot_match, lexical)


def recency(row: Dict[str, Any], now: datetime) -> float:
    hl = REC_HALF_LIFE.get(row["memory_type"], REC_DEFAULT_HL)
    return 0.5 ** ((now - from_iso(row["last_confirmed_at"])).days / hl)


def rank(cands: Dict[str, Cand], q: Query, now: datetime) -> List[Scored]:
    scored = []
    for c in cands.values():
        m = c.row
        rel = relevance(c, q)
        conf = effective_confidence(m["memory_type"], m["confidence"], m["last_confirmed_at"], now)
        rec = recency(m, now)
        s = W_REL * rel + W_IMP * m["importance"] + W_CONF * conf + W_REC * rec
        drop = ("REL_FLOOR" if rel < REL_FLOOR and not c.reserved else
                "SCORE_FLOOR" if s < SCORE_FLOOR and not c.reserved else None)
        scored.append(Scored(c, r2(rel), m["importance"], r2(conf), r2(rec), r2(s), drop))
    scored.sort(key=lambda x: (-x.score, x.c.row["id"]))
    return scored


def select(ranked: List[Scored]) -> List[Scored]:
    live = [r for r in ranked if not r.drop]
    picked: List[Scored] = []
    tokens, used_slots = 0, set()
    constraints = [r for r in live if r.c.row["memory_type"] == "constraint"][:CONSTRAINT_RESERVE]
    for r in constraints + [r for r in live if r not in constraints]:
        if r.c.row["slot_key"] in used_slots:
            continue  # one item per slot (contested pair = one item)
        t = approx_tokens(render_item(Item(r.c.row, r.c.contested_sibling), "m0"))
        if len(picked) >= K_MAX or tokens + t > TOKEN_BUDGET:
            break
        picked.append(r)
        tokens += t
        used_slots.add(r.c.row["slot_key"])
    return picked


# ---------------------------------------------------------------------------
# Debug-only filter view (§24.1)
# ---------------------------------------------------------------------------


def first_failed_filter(row: Dict[str, Any], f: Filters, now_iso: str) -> str:
    if row["status"] not in f.statuses:
        return f"status={row['status']}"
    if f.not_expired and row["expires_at"] and row["expires_at"] <= now_iso:
        return "expired"
    if row["sensitivity"] not in f.sensitivity:
        return f"sensitivity={row['sensitivity']}"
    if f.types and row["memory_type"] not in f.types:
        return f"type={row['memory_type']}"
    return "allowed_use"


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------


class Retriever:
    def __init__(self, store: MemoryStore, sink: EventSink, *, debug_events: bool = False):
        self.store = store
        self.sink = sink
        self.debug_events = debug_events

    def retrieve_block(self, scope: MemoryScope, llm_safe_text: str, source_kind: str, trace_id: str,
                       now: Optional[datetime] = None) -> Tuple[str, List[Item]]:
        now = now or utcnow()
        now_iso = to_iso(now)
        emit = lambda *a, **k: self.sink.emit(scope, trace_id, *a, **k)  # noqa: E731
        q = build_query(llm_safe_text)
        f = allowed_filters(source_kind, q)
        # Counts + predicate families only (deep dive §24 table): raw query terms/entities would retain user values.
        emit("retrieve.query", detail={"n_terms": len(q.terms), "families": q.families, "n_entities": len(q.entities),
                                       "hard_filters": f.as_dict(scope)})
        with self.store.read() as conn:
            cands, counts = candidates(conn, scope, q, f, now_iso)
            if self.debug_events:
                passed = set(cands) | {c.contested_sibling["id"] for c in cands.values() if c.contested_sibling}
                debug_f = Filters(statuses=ALL_STATUSES, not_expired=False, sensitivity=("low", "medium", "high"))
                for m in sql_by_predicates(conn, scope, q.families, debug_f, now_iso):
                    if m["id"] not in passed:
                        emit("retrieve.filter", memory_id=m["id"], decision="EXCLUDED",
                             detail={"filter": first_failed_filter(m, f, now_iso), "slot_key": m["slot_key"]},
                             safe_text=m["canonical_text"],
                             dev_detail={"display": vocab.display_value(m["predicate"], m["value_json"])})
        emit("retrieve.candidates", detail=counts)

        ranked = rank(cands, q, now)
        picked = select(ranked)
        items = [Item(r.c.row, r.c.contested_sibling) for r in picked]

        # P2 egress: SQL filters already excluded disallowed rows, so a hit means a write-path bug.
        bad = [it for it in items if privacy.egress_findings(render_item(it, "m0"))]
        if bad:
            emit("privacy.egress", decision="DROP", reason_codes=["EGRESS_VIOLATION"], detail={"count": len(bad)})
            items = [it for it in items if it not in bad]
        elif items:
            emit("privacy.egress", decision="PASS", detail={"count": len(items)})
        picked_ids = {it.row["id"] for it in items}

        for r in ranked:
            m = r.c.row
            selected = m["id"] in picked_ids
            emit("retrieve.rank", memory_id=m["id"], decision="SELECTED" if selected else "DROPPED",
                 detail={"rel": r.rel, "imp": r.imp, "conf": r.conf, "rec": r.rec, "total": r.score,
                         "drop": r.drop if r.drop or selected else "NOT_SELECTED", "generators": r.c.generators},
                 safe_text=m["canonical_text"],
                 dev_detail={"display": vocab.display_value(m["predicate"], m["value_json"])})

        block = render_block(items)
        for it in items:
            emit("prompt.render", memory_id=it.row["id"],
                 detail={"alias": it.alias, "tokens": approx_tokens(render_item(it, it.alias or "m0"))})
        emit("retrieve.select",
             detail={"selected": [{"alias": it.alias, "memory_id": it.row["id"]} for it in items],
                     "tokens": approx_tokens(block) if block else 0},
             safe_text=block)
        if items:
            with self.store.write() as conn:  # observability only; not a ranking input
                for it in items:
                    conn.execute("UPDATE memories SET retrieval_count=retrieval_count+1, last_accessed_at=? "
                                 "WHERE id=? AND user_id=?", (now_iso, it.row["id"], scope.user_id))
        return block, items
