"""SQLite store for long-term memory (deep dive §0.1, §13, §21, §22, §23).

Connection discipline follows ``TriggerStore`` (handoff C9): one short-lived connection per operation,
``isolation_level=None``, explicit ``BEGIN IMMEDIATE`` for writes, and the connection-scoped pragmas
(``secure_delete``, ``foreign_keys``) applied on every connection. WAL is set once at schema creation.

Every public method takes a ``MemoryScope`` first; no method accepts a bare user id (§23).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, List, Optional, Sequence

from .models import MemoryScope, NewRecord, new_id, to_iso, utcnow

if TYPE_CHECKING:  # pragma: no cover
    from .models import Outcome, TurnRef

# Deep dive §0.1, verbatim.
DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA secure_delete = ON;        -- zero freed pages (baseline S1: DELETE left bytes in triggers.db/WAL)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS memory_users (
  user_id     TEXT PRIMARY KEY,
  epoch       INTEGER NOT NULL DEFAULT 0,      -- fencing token, bumped by forget-all / clear-chat
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
  id                  TEXT PRIMARY KEY,         -- 'mem_' + ULID
  user_id             TEXT NOT NULL REFERENCES memory_users(user_id),
  memory_type         TEXT NOT NULL CHECK (memory_type IN
                        ('profile','preference','constraint','relationship','project')),
  subject             TEXT NOT NULL,            -- 'user' | 'person:alice' | 'project:openpoke-memory'
  predicate           TEXT NOT NULL,            -- 'pref.meeting_time'
  slot_key            TEXT NOT NULL,            -- 'user|pref.meeting_time' or 'user|constraint.confirm_before_email|person:bob'
  cardinality         TEXT NOT NULL CHECK (cardinality IN ('single','multi')),
  value_json          TEXT,                     -- canonical value; NULL once purged
  value_hmac          TEXT NOT NULL,            -- HMAC(server_key, user_id|slot_key|canonical_value); survives purge
  canonical_text      TEXT,                     -- MEMORY_SAFE sentence; NULL once purged
  status              TEXT NOT NULL CHECK (status IN
                        ('active','contested','superseded','expired','deleted','quarantined')),
  importance          REAL NOT NULL,
  confidence          REAL NOT NULL,
  sensitivity         TEXT NOT NULL CHECK (sensitivity IN ('low','medium','high')),
  pii_categories      TEXT NOT NULL DEFAULT '[]',
  allowed_uses        TEXT NOT NULL DEFAULT '["interaction_context"]',
  source_kind         TEXT NOT NULL CHECK (source_kind IN ('user_message')),
  source_turn_id      TEXT NOT NULL,
  observed_at         TEXT NOT NULL,            -- when the user said it (UTC ISO-8601)
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL,
  last_confirmed_at   TEXT NOT NULL,
  last_accessed_at    TEXT,
  expires_at          TEXT,
  supersedes_id       TEXT REFERENCES memories(id),
  superseded_by_id    TEXT REFERENCES memories(id),
  superseded_at       TEXT,
  contests_id         TEXT REFERENCES memories(id),
  related_id          TEXT REFERENCES memories(id),
  deleted_at          TEXT,
  version             INTEGER NOT NULL DEFAULT 1,
  reinforcement_count INTEGER NOT NULL DEFAULT 0,
  retrieval_count     INTEGER NOT NULL DEFAULT 0,
  extractor_version   TEXT NOT NULL,
  policy_version      TEXT NOT NULL,
  CHECK (status <> 'deleted' OR (canonical_text IS NULL AND value_json IS NULL))
);

-- THE supersession invariant: at most one active value per single-valued slot.
CREATE UNIQUE INDEX IF NOT EXISTS ux_one_active_single_slot
  ON memories(user_id, slot_key) WHERE status = 'active' AND cardinality = 'single';
-- Multi-valued slots: no duplicate active values.
CREATE UNIQUE INDEX IF NOT EXISTS ux_active_multi_value
  ON memories(user_id, slot_key, value_hmac) WHERE status = 'active' AND cardinality = 'multi';
CREATE INDEX IF NOT EXISTS ix_mem_user_status_type ON memories(user_id, status, memory_type);
CREATE INDEX IF NOT EXISTS ix_mem_user_slot        ON memories(user_id, slot_key);
CREATE INDEX IF NOT EXISTS ix_mem_expiry           ON memories(status, expires_at);

-- Index holds ONLY retrievable rows (active + contested). Maintained in the same transaction.
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  canonical_text, keywords, memory_id UNINDEXED, user_id UNINDEXED,
  tokenize = 'porter unicode61'
);
INSERT INTO memories_fts(memories_fts, rank) VALUES ('secure-delete', 1);  -- FTS5 ≥ 3.42: purge deleted tokens

CREATE TABLE IF NOT EXISTS memory_tombstones (
  id          INTEGER PRIMARY KEY,
  user_id     TEXT NOT NULL,
  slot_key    TEXT,                 -- NULL for forget-all
  value_hmac  TEXT,                 -- NULL for slot-wide tombstones
  scope       TEXT NOT NULL CHECK (scope IN ('slot','value','all')),
  deleted_at  TEXT NOT NULL,
  epoch       INTEGER NOT NULL,
  reason      TEXT NOT NULL         -- 'user_forget' | 'user_negation' | 'api' | 'forget_all'
);
CREATE INDEX IF NOT EXISTS ix_tomb_slot  ON memory_tombstones(user_id, slot_key);
CREATE INDEX IF NOT EXISTS ix_tomb_value ON memory_tombstones(user_id, value_hmac);

CREATE TABLE IF NOT EXISTS memory_events (
  event_id     TEXT PRIMARY KEY,
  trace_id     TEXT NOT NULL,
  user_ref     TEXT NOT NULL,       -- HMAC of user_id
  ts           TEXT NOT NULL,
  stage        TEXT NOT NULL,
  candidate_id TEXT,
  memory_id    TEXT,
  decision     TEXT,
  reason_codes TEXT NOT NULL DEFAULT '[]',
  detail_json  TEXT NOT NULL DEFAULT '{}',   -- LOG_SAFE: scores, detector types/counts, versions
  safe_text    TEXT                          -- MEMORY_SAFE text, dev mode only, nulled on delete
);
CREATE INDEX IF NOT EXISTS ix_events_trace  ON memory_events(trace_id);
CREATE INDEX IF NOT EXISTS ix_events_memory ON memory_events(memory_id);
"""

FTS_SECURE_DELETE_MIN = (3, 42, 0)
RETRIEVABLE = ("active", "contested")
PURGE_AFTER_DAYS = {"superseded": 30, "expired": 7}  # deep dive §13
EVENT_DEV_RETENTION_DAYS = 7  # deep dive §24: "a retention of 7 days for events in dev"

_MEMORY_COLUMNS = (
    "id", "user_id", "memory_type", "subject", "predicate", "slot_key", "cardinality", "value_json", "value_hmac",
    "canonical_text", "status", "importance", "confidence", "sensitivity", "pii_categories", "source_kind",
    "source_turn_id", "observed_at", "created_at", "updated_at", "last_confirmed_at", "expires_at",
    "supersedes_id", "contests_id", "related_id", "extractor_version", "policy_version",
)


class _FenceRollback(Exception):
    """Raised inside a write() to roll the fenced transaction back."""


def _sqlite_version() -> tuple:
    return tuple(int(p) for p in sqlite3.sqlite_version.split(".")[:3])


class MemoryStore:
    """Low-level persistence for LTM. Thread-safe via short-lived connections and SQLite locking."""

    def __init__(self, db_path: Path, hmac_key: Optional[bytes] = None, *, test_mode: bool = False):
        self.db_path = Path(db_path)
        self.test_mode = test_mode
        self._hmac_key = hmac_key
        self._key_lock = threading.Lock()
        self.fts_secure_delete = _sqlite_version() >= FTS_SECURE_DELETE_MIN
        self.secure_delete_supported = True
        self.fallbacks: List[str] = []
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # ------------------------------------------------------------------ connections

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA secure_delete = ON")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _ensure_schema(self) -> None:
        ddl = DDL
        if not self.fts_secure_delete:
            # Pre-approved fallback (handoff §2): 'optimize' after each delete instead.
            ddl = ddl.replace("INSERT INTO memories_fts(memories_fts, rank) VALUES ('secure-delete', 1);", "")
            self.fallbacks.append("fts5_secure_delete_unavailable:optimize_after_delete")
        conn = self._connect()
        try:
            conn.executescript(ddl)
            row = conn.execute("PRAGMA secure_delete").fetchone()
            if not row or int(row[0]) != 1:
                self.secure_delete_supported = False
                self.fallbacks.append("pragma_secure_delete_unsupported:vacuum_after_delete_in_test_mode")
        finally:
            conn.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """``BEGIN IMMEDIATE`` transaction: one writer at a time; rollback on any exception."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
        finally:
            conn.close()

    # ------------------------------------------------------------------ keys

    def _key(self) -> bytes:
        """C11: env key, else ``.hmac_key`` next to the DB (32 random bytes, mode 0600). Never logged."""
        if self._hmac_key is not None:
            return self._hmac_key
        with self._key_lock:
            if self._hmac_key is not None:
                return self._hmac_key
            env = os.getenv("OPENPOKE_LTM_HMAC_KEY")
            if env:
                self._hmac_key = env.encode("utf-8")
                return self._hmac_key
            path = self.db_path.parent / ".hmac_key"
            try:
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                self._hmac_key = path.read_bytes()
            else:
                key = os.urandom(32)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(key)
                self._hmac_key = key
            return self._hmac_key

    def _hmac(self, message: str) -> str:
        return hmac.new(self._key(), message.encode("utf-8"), hashlib.sha256).hexdigest()

    def value_hmac(self, scope: MemoryScope, slot_key: str, canonical_value: str) -> str:
        return self._hmac(f"{scope.user_id}|{slot_key}|{canonical_value}")

    def user_ref(self, scope: MemoryScope) -> str:
        return "u_" + self._hmac(f"user|{scope.user_id}")[:24]

    # ------------------------------------------------------------------ users / epoch

    def ensure_user(self, conn: sqlite3.Connection, scope: MemoryScope) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO memory_users(user_id, epoch, created_at) VALUES (?, 0, ?)",
            (scope.user_id, to_iso(utcnow())),
        )

    def epoch_in(self, conn: sqlite3.Connection, scope: MemoryScope) -> int:
        row = conn.execute("SELECT epoch FROM memory_users WHERE user_id=?", (scope.user_id,)).fetchone()
        return int(row[0]) if row else 0

    def epoch(self, scope: MemoryScope) -> int:
        with self.read() as conn:
            return self.epoch_in(conn, scope)

    def bump_epoch(self, scope: MemoryScope) -> int:
        with self.write() as conn:
            self.ensure_user(conn, scope)
            conn.execute("UPDATE memory_users SET epoch = epoch + 1 WHERE user_id=?", (scope.user_id,))
            return self.epoch_in(conn, scope)

    # ------------------------------------------------------------------ row writes (inside a write())

    def insert_row(
        self,
        conn: sqlite3.Connection,
        scope: MemoryScope,
        rec: NewRecord,
        *,
        status: str,
        supersedes_id: Optional[str] = None,
        contests_id: Optional[str] = None,
    ) -> str:
        self.ensure_user(conn, scope)
        now = to_iso(utcnow())
        mem_id = new_id("mem")
        values = {
            "id": mem_id,
            "user_id": scope.user_id,
            "memory_type": rec.slot.memory_type,
            "subject": rec.slot.subject,
            "predicate": rec.slot.predicate,
            "slot_key": rec.slot.slot_key,
            "cardinality": rec.slot.cardinality,
            "value_json": rec.value_json,
            "value_hmac": rec.value_hmac,
            "canonical_text": rec.canonical_text,
            "status": status,
            "importance": rec.importance,
            "confidence": rec.confidence,
            "sensitivity": rec.sensitivity,
            "pii_categories": json.dumps(sorted(rec.pii_categories)),
            "source_kind": rec.source_kind,
            "source_turn_id": rec.source_turn_id,
            "observed_at": rec.observed_at,
            "created_at": now,
            "updated_at": now,
            "last_confirmed_at": rec.observed_at,
            "expires_at": rec.expires_at,
            "supersedes_id": supersedes_id,
            "contests_id": contests_id,
            "related_id": rec.related_id,
            "extractor_version": rec.extractor_version,
            "policy_version": rec.policy_version,
        }
        cols = ", ".join(_MEMORY_COLUMNS)
        marks = ", ".join(":" + c for c in _MEMORY_COLUMNS)
        conn.execute(f"INSERT INTO memories ({cols}) VALUES ({marks})", values)
        return mem_id

    def index_row(
        self, conn: sqlite3.Connection, scope: MemoryScope, memory_id: str, canonical_text: str, keywords: str
    ) -> None:
        conn.execute(
            "INSERT INTO memories_fts(canonical_text, keywords, memory_id, user_id) VALUES (?,?,?,?)",
            (canonical_text, keywords, memory_id, scope.user_id),
        )

    def unindex_row(self, conn: sqlite3.Connection, scope: MemoryScope, memory_id: str) -> None:
        conn.execute("DELETE FROM memories_fts WHERE memory_id=? AND user_id=?", (memory_id, scope.user_id))

    # ------------------------------------------------------------------ reads

    def get_memory(self, scope: MemoryScope, memory_id: str) -> Optional[Dict[str, Any]]:
        with self.read() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE user_id=? AND id=?", (scope.user_id, memory_id)
            ).fetchone()
        return dict(row) if row else None

    def all_rows(self, scope: MemoryScope) -> List[Dict[str, Any]]:
        with self.read() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id=? ORDER BY created_at, id", (scope.user_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def rows_in_slot(
        self, scope: MemoryScope, slot_key: str, statuses: Optional[Sequence[str]] = None
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM memories WHERE user_id=? AND slot_key=?"
        params: List[Any] = [scope.user_id, slot_key]
        if statuses:
            sql += f" AND status IN ({','.join('?' * len(statuses))})"
            params.extend(statuses)
        with self.read() as conn:
            rows = conn.execute(sql + " ORDER BY created_at, id", params).fetchall()
        return [dict(r) for r in rows]

    def slot_keys(self, scope: MemoryScope, statuses: Sequence[str] = RETRIEVABLE) -> List[str]:
        with self.read() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT slot_key FROM memories WHERE user_id=? AND status IN ({','.join('?' * len(statuses))})"
                " ORDER BY slot_key",
                [scope.user_id, *statuses],
            ).fetchall()
        return [r[0] for r in rows]

    def fts_memory_ids(self, scope: MemoryScope) -> List[str]:
        with self.read() as conn:
            rows = conn.execute("SELECT memory_id FROM memories_fts WHERE user_id=?", (scope.user_id,)).fetchall()
        return [r[0] for r in rows]

    def tombstones(self, scope: MemoryScope) -> List[Dict[str, Any]]:
        with self.read() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_tombstones WHERE user_id=? ORDER BY id", (scope.user_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ deletion (§21)

    # Dev-mode MEMORY_SAFE keys that may sit in detail_json (events.emit dev_detail).
    _DEV_DETAIL_KEYS = ("display", "reason", "terms", "entities", "label_value")

    def _scrub_event_rows(self, conn: sqlite3.Connection, event_ids: Sequence[str]) -> None:
        for eid in event_ids:
            row = conn.execute("SELECT detail_json FROM memory_events WHERE event_id=?", (eid,)).fetchone()
            if row is None:
                continue
            detail = json.loads(row[0] or "{}")
            for k in self._DEV_DETAIL_KEYS:
                detail.pop(k, None)
            conn.execute("UPDATE memory_events SET safe_text=NULL, detail_json=? WHERE event_id=?",
                         (json.dumps(detail, sort_keys=True), eid))

    def _linked_event_ids(self, conn: sqlite3.Connection, scope: MemoryScope, memory_ids: Sequence[str]) -> List[str]:
        """Every event that can carry a deleted memory's text: its own events, the candidate events that produced
        it (same trace + candidate id: extract.clause / privacy.classify / policy / validate), and the rendered
        blocks (retrieve.select) that included it."""
        if not memory_ids:
            return []
        ref = self.user_ref(scope)
        marks = ",".join("?" * len(memory_ids))
        ids = {r[0] for r in conn.execute(
            f"SELECT event_id FROM memory_events WHERE user_ref=? AND memory_id IN ({marks})", [ref, *memory_ids])}
        for trace_id, cand_id in conn.execute(
                f"SELECT DISTINCT trace_id, candidate_id FROM memory_events WHERE user_ref=? AND memory_id IN ({marks})"
                " AND candidate_id IS NOT NULL", [ref, *memory_ids]).fetchall():
            ids |= {r[0] for r in conn.execute(
                "SELECT event_id FROM memory_events WHERE user_ref=? AND trace_id=? AND candidate_id=?",
                (ref, trace_id, cand_id))}
        for eid, detail in conn.execute(
                "SELECT event_id, detail_json FROM memory_events WHERE user_ref=? AND stage='retrieve.select'",
                (ref,)).fetchall():
            if any(m in (detail or "") for m in memory_ids):
                ids.add(eid)
        return sorted(ids)

    @staticmethod
    def _value_needles(row: Dict[str, Any]) -> List[str]:
        """Every surface form of a memory's value that a debug event could carry: canonical text, display phrase,
        the canonical value (HH:MM, slug) and the entity name (review M2)."""
        from . import vocab

        out = [row.get("canonical_text") or ""]
        out.append(vocab.display_value(row["predicate"], row.get("value_json")) or "")
        try:
            v = json.loads(row["value_json"]) if row.get("value_json") else None
        except ValueError:
            v = None
        if isinstance(v, dict):
            for x in v.values():
                for t in (x if isinstance(x, list) else [x]):
                    if isinstance(t, str) and re.fullmatch(r"\d{2}:\d{2}", t):
                        out += [t, vocab.fmt_time(t)]
                    elif isinstance(t, str):
                        out.append(t)
        elif isinstance(v, str):
            out += [v, v.replace("-", " ")]
        return sorted({n.strip() for n in out if n and len(n.strip()) >= 3}, key=len, reverse=True)

    def _value_event_ids(self, conn: sqlite3.Connection, scope: MemoryScope, rows: Sequence[Dict[str, Any]]) -> List[str]:
        ids: List[str] = []
        ref = self.user_ref(scope)
        for row in rows:
            for needle in self._value_needles(row):
                ids += [r[0] for r in conn.execute(
                    "SELECT event_id FROM memory_events WHERE user_ref=? AND "
                    "instr(lower(COALESCE(safe_text,'') || ' ' || detail_json), lower(?)) > 0", (ref, needle))]
        return ids

    def scrub_job_events(self, scope: MemoryScope, trace_id: str, candidate_id: str) -> None:
        """A tombstoned (fence-dropped) job must not leave the forgotten text behind in its own events."""
        with self.write() as conn:
            ids = [r[0] for r in conn.execute(
                "SELECT event_id FROM memory_events WHERE user_ref=? AND trace_id=? AND candidate_id=?",
                (self.user_ref(scope), trace_id, candidate_id))]
            self._scrub_event_rows(conn, ids)
        self.checkpoint_truncate()


    def _insert_tombstone(
        self,
        conn: sqlite3.Connection,
        scope: MemoryScope,
        *,
        tomb_scope: str,
        slot_key: Optional[str],
        value_hmac: Optional[str],
        reason: str,
        deleted_at: str,
    ) -> None:
        conn.execute(
            "INSERT INTO memory_tombstones(user_id,slot_key,value_hmac,scope,deleted_at,epoch,reason)"
            " VALUES (?,?,?,?,?,?,?)",
            (scope.user_id, slot_key, value_hmac, tomb_scope, deleted_at, self.epoch_in(conn, scope), reason),
        )

    def purge_slot(self, scope: MemoryScope, slot_key: str, reason: str) -> Dict[str, Any]:
        """Delete the whole slot chain: content NULL, FTS row removed, event text scrubbed, slot + value tombstones.

        Writes the slot tombstone even when the slot holds no row yet (D27). Returns ids and the tombstone time.
        """
        now = to_iso(utcnow())
        with self.write() as conn:
            self.ensure_user(conn, scope)
            rows = conn.execute(
                "SELECT id, value_hmac, predicate, value_json, canonical_text FROM memories"
                " WHERE user_id=? AND slot_key=? AND status<>'deleted'",
                (scope.user_id, slot_key),
            ).fetchall()
            linked = self._linked_event_ids(conn, scope, [r["id"] for r in rows])
            self._scrub_event_rows(conn, sorted(set(linked) | set(self._value_event_ids(conn, scope, [dict(r) for r in rows]))))
            for r in rows:
                conn.execute(
                    "UPDATE memories SET status='deleted', canonical_text=NULL, value_json=NULL,"
                    " deleted_at=?, updated_at=?, version=version+1 WHERE id=? AND user_id=?",
                    (now, now, r["id"], scope.user_id),
                )
                self.unindex_row(conn, scope, r["id"])
                self._insert_tombstone(
                    conn, scope, tomb_scope="value", slot_key=slot_key, value_hmac=r["value_hmac"],
                    reason=reason, deleted_at=now,
                )
            self._insert_tombstone(
                conn, scope, tomb_scope="slot", slot_key=slot_key, value_hmac=None, reason=reason, deleted_at=now
            )
        self._after_delete()
        return {"deleted_ids": [r["id"] for r in rows], "deleted_at": now}

    def forget_all(self, scope: MemoryScope) -> Dict[str, Any]:
        now = to_iso(utcnow())
        with self.write() as conn:
            self.ensure_user(conn, scope)
            conn.execute("UPDATE memory_users SET epoch = epoch + 1 WHERE user_id=?", (scope.user_id,))
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM memories WHERE user_id=? AND status<>'deleted'", (scope.user_id,)
            ).fetchall()]
            conn.execute(
                "UPDATE memories SET status='deleted', canonical_text=NULL, value_json=NULL, deleted_at=?,"
                " updated_at=?, version=version+1 WHERE user_id=? AND status<>'deleted'",
                (now, now, scope.user_id),
            )
            conn.execute("DELETE FROM memories_fts WHERE user_id=?", (scope.user_id,))
            self._scrub_event_rows(conn, [r[0] for r in conn.execute(
                "SELECT event_id FROM memory_events WHERE user_ref=?", (self.user_ref(scope),))])
            self._insert_tombstone(
                conn, scope, tomb_scope="all", slot_key=None, value_hmac=None, reason="forget_all", deleted_at=now
            )
        self._after_delete()
        return {"deleted_ids": ids, "deleted_at": now}

    def _after_delete(self) -> None:
        if not self.fts_secure_delete:
            with self.write() as conn:
                conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('optimize')")
        if not self.secure_delete_supported and self.test_mode:
            with self.read() as conn:
                conn.execute("VACUUM")
        self.checkpoint_truncate()

    def checkpoint_truncate(self) -> None:
        with self.read() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # ------------------------------------------------------------------ fenced commit (§22)

    def commit_candidate(self, turn: "TurnRef", rec: NewRecord, keywords: str) -> "Outcome":
        """Epoch + tombstone fence and consolidation in ONE ``BEGIN IMMEDIATE`` transaction (no check-then-act gap)."""
        from .consolidate import RetryConsolidate, consolidate  # consolidate imports this module
        from .models import ConsolidationOutcome as CO
        from .models import Outcome

        scope = turn.scope
        job_observed = turn.observed_iso
        for _attempt in range(3):
            fence: Optional[Outcome] = None
            try:
                with self.write() as conn:
                    self.ensure_user(conn, scope)
                    current_epoch = self.epoch_in(conn, scope)
                    if current_epoch != turn.epoch:
                        fence = Outcome(CO.FENCE_DROP, reason_codes=["EPOCH_CHANGED"], detail={
                            "slot_key": rec.slot_key,
                            "refs": {"job_epoch": turn.epoch, "current_epoch": current_epoch,
                                     "job_observed_at": job_observed}})
                        raise _FenceRollback()
                    t = conn.execute(
                        "SELECT MAX(deleted_at) FROM memory_tombstones WHERE user_id=? AND (scope='all'"
                        " OR (scope='slot' AND slot_key=?) OR (scope='value' AND value_hmac=?))",
                        (scope.user_id, rec.slot_key, rec.value_hmac),
                    ).fetchone()[0]
                    if t and t >= job_observed:
                        fence = Outcome(CO.FENCE_DROP, reason_codes=["TOMBSTONED"], detail={
                            "slot_key": rec.slot_key,
                            "refs": {"job_observed_at": job_observed, "tombstone_at": t}})
                        raise _FenceRollback()
                    out = consolidate(self, conn, scope, rec)
                    if out.kind in (CO.INSERT, CO.SUPERSEDE, CO.CONTEST):
                        self.index_row(conn, scope, out.memory_id, rec.canonical_text, keywords)
                    return out
            except _FenceRollback:
                return fence  # type: ignore[return-value]
            except RetryConsolidate:
                continue
        raise RuntimeError("consolidation kept conflicting; giving up after 3 attempts")

    # ------------------------------------------------------------------ TTL sweep (§13)

    def sweep(self, now: Optional[datetime] = None, on_expire: Optional[Callable[[str], None]] = None) -> List[str]:
        """Expire due rows (all users) and purge content past the grace windows. Startup + hourly."""
        from datetime import timedelta

        now_dt = now or utcnow()
        now_iso = to_iso(now_dt)
        expired: List[str] = []
        with self.write() as conn:
            rows = conn.execute(
                "SELECT id FROM memories WHERE status IN ('active','contested') AND expires_at IS NOT NULL"
                " AND expires_at <= ?",
                (now_iso,),
            ).fetchall()
            for r in rows:
                conn.execute(
                    "UPDATE memories SET status='expired', version=version+1, updated_at=? WHERE id=?",
                    (now_iso, r["id"]),
                )
                conn.execute("DELETE FROM memories_fts WHERE memory_id=?", (r["id"],))
                expired.append(r["id"])
            for status, days in PURGE_AFTER_DAYS.items():
                cutoff = to_iso(now_dt - timedelta(days=days))
                purged = [p[0] for p in conn.execute(
                    "SELECT id FROM memories WHERE status=? AND canonical_text IS NOT NULL"
                    " AND COALESCE(superseded_at, updated_at) <= ?",
                    (status, cutoff),
                ).fetchall()]
                for mem_id in purged:
                    conn.execute(
                        "UPDATE memories SET canonical_text=NULL, value_json=NULL WHERE id=?", (mem_id,)
                    )
                    conn.execute("UPDATE memory_events SET safe_text=NULL WHERE memory_id=?", (mem_id,))
                    ev = conn.execute("SELECT DISTINCT user_ref, trace_id, candidate_id FROM memory_events"
                                      " WHERE memory_id=? AND candidate_id IS NOT NULL", (mem_id,)).fetchall()
                    for ref, trace_id, cand in ev:
                        self._scrub_event_rows(conn, [r[0] for r in conn.execute(
                            "SELECT event_id FROM memory_events WHERE user_ref=? AND trace_id=? AND candidate_id=?",
                            (ref, trace_id, cand))])
            # Deep dive §24: dev-mode event content (safe_text + MEMORY_SAFE dev keys) is retained 7 days.
            cutoff = to_iso(now_dt - timedelta(days=EVENT_DEV_RETENTION_DAYS))
            old_events = [r[0] for r in conn.execute(
                "SELECT event_id FROM memory_events WHERE ts <= ? AND (safe_text IS NOT NULL OR detail_json LIKE '%\"display\"%'"
                " OR detail_json LIKE '%\"reason\"%' OR detail_json LIKE '%\"label_value\"%')", (cutoff,))]
            self._scrub_event_rows(conn, old_events)
        if on_expire:
            for mem_id in expired:
                on_expire(mem_id)
        self.checkpoint_truncate()
        return expired
