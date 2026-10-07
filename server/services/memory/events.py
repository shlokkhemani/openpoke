"""Event sink (design §17, deep dive §24): ``memory_events`` table + optional JSONL. LOG_SAFE by construction."""

from __future__ import annotations

import itertools
import json
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import MemoryScope, to_iso, ulid, utcnow
from .privacy import prohibited_findings
from .store import MemoryStore

STAGES = (
    "ingest", "ingress.scrub", "privacy.scrub", "forget.detect", "forget.apply", "extract", "extract.clause",
    "validate", "privacy.classify", "policy", "consolidate", "store", "index", "fence_drop", "retrieve.query",
    "retrieve.filter", "retrieve.candidates", "retrieve.rank", "retrieve.select", "privacy.egress",
    "prompt.render", "expire", "purge",
)
REJECT_DECISIONS = {"REJECT", "QUARANTINE"}
# REJECT events carry detector types and counts only: never the value, its length or its position.
_REJECT_FORBIDDEN_DETAIL = {"value", "length", "offset", "start", "end", "span", "chars", "text", "evidence"}

_seq = itertools.count()
_seq_lock = threading.Lock()


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _event_id() -> str:
    # ULID time prefix + process-monotonic counter (base32, after an 'S' separator so no long digit run can look
    # like a phone number): ORDER BY ts, event_id is stable within a millisecond.
    with _seq_lock:
        n = next(_seq)
    digits = []
    for _ in range(9):
        digits.append(_CROCKFORD[n & 31])
        n >>= 5
    return f"evt_{ulid()[:10]}S{''.join(reversed(digits))}"


class EventSink:
    def __init__(self, store: MemoryStore, *, debug_events: bool = False, jsonl_path: Optional[Path] = None):
        self.store = store
        self.debug_events = debug_events
        self.jsonl_path = Path(jsonl_path) if jsonl_path else None
        self._jsonl_lock = threading.Lock()

    def emit(
        self,
        scope: MemoryScope,
        trace_id: Optional[str],
        stage: str,
        *,
        candidate_id: Optional[str] = None,
        memory_id: Optional[str] = None,
        decision: Optional[str] = None,
        reason_codes: Iterable[str] = (),
        detail: Optional[Dict[str, Any]] = None,
        safe_text: Optional[str] = None,
        dev_detail: Optional[Dict[str, Any]] = None,
    ) -> str:
        """``detail`` is LOG_SAFE. ``safe_text`` and ``dev_detail`` (MEMORY_SAFE display fields such as query terms
        or a value phrase) are kept only when debug events are on, and never on REJECT."""
        if stage not in STAGES:
            raise ValueError(f"unknown event stage {stage!r}")
        detail = dict(detail or {})
        if dev_detail and self.debug_events and decision not in REJECT_DECISIONS:
            detail.update(dev_detail)
        if decision in REJECT_DECISIONS:
            safe_text = None
            detail = {k: v for k, v in detail.items() if k not in _REJECT_FORBIDDEN_DETAIL}
        if not self.debug_events:
            safe_text = None
        reasons = list(reason_codes)
        detail_json = json.dumps(detail, sort_keys=True, default=str)
        # Last line of defence: an event must never carry a prohibited-class value.
        if (safe_text and prohibited_findings(safe_text)) or prohibited_findings(detail_json):
            safe_text = None
            detail_json = json.dumps({"redacted": True})
            reasons.append("EGRESS_VIOLATION")
        row = {
            "event_id": _event_id(),
            "trace_id": trace_id or "sys",
            "user_ref": self.store.user_ref(scope),
            "ts": to_iso(utcnow()),
            "stage": stage,
            "candidate_id": candidate_id,
            "memory_id": memory_id,
            "decision": decision,
            "reason_codes": json.dumps(reasons),
            "detail_json": detail_json,
            "safe_text": safe_text,
        }
        with self.store.write() as conn:
            conn.execute(
                "INSERT INTO memory_events(event_id,trace_id,user_ref,ts,stage,candidate_id,memory_id,decision,"
                "reason_codes,detail_json,safe_text) VALUES (:event_id,:trace_id,:user_ref,:ts,:stage,:candidate_id,"
                ":memory_id,:decision,:reason_codes,:detail_json,:safe_text)",
                row,
            )
        if self.jsonl_path:
            with self._jsonl_lock:
                self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
                with self.jsonl_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, sort_keys=True) + "\n")
        return row["event_id"]

    # ------------------------------------------------------------------ reads

    @staticmethod
    def _decode(row: Any) -> Dict[str, Any]:
        d = dict(row)
        d["reason_codes"] = json.loads(d["reason_codes"] or "[]")
        d["detail"] = json.loads(d.pop("detail_json") or "{}")
        return d

    def events(self, scope: MemoryScope, trace_id: str) -> List[Dict[str, Any]]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_events WHERE user_ref=? AND trace_id=? ORDER BY ts, event_id",
                (self.store.user_ref(scope), trace_id),
            ).fetchall()
        return [self._decode(r) for r in rows]

    def events_for_memory(self, scope: MemoryScope, memory_ids: Iterable[str]) -> List[Dict[str, Any]]:
        ids = list(memory_ids)
        if not ids:
            return []
        with self.store.read() as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_events WHERE user_ref=? AND (memory_id IN ({','.join('?' * len(ids))})"
                " OR stage IN ('consolidate','forget.apply','expire')) ORDER BY ts, event_id",
                [self.store.user_ref(scope), *ids],
            ).fetchall()
        return [self._decode(r) for r in rows]

    def stage_events(self, scope: MemoryScope, stage: str) -> List[Dict[str, Any]]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_events WHERE user_ref=? AND stage=? ORDER BY ts, event_id",
                (self.store.user_ref(scope), stage),
            ).fetchall()
        return [self._decode(r) for r in rows]
