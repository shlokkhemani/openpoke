"""MemoryService (deep dive §1): synchronous ``prepare_turn`` + asynchronous, fenced ``schedule_ingest``.

C8: ``prepare_turn`` is synchronous and lock-free (``handle_agent_message`` may run under a different event loop).
Per-user ingest locks are created lazily per running loop; an ``asyncio.Lock`` is never shared across loops.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import forget as forget_mod
from . import policy, privacy, vocab
from .consolidate import keywords_for_row
from .detectors import counts
from .events import EventSink
from .extractor import Extractor, RuleExtractor, report_clauses, split_clauses, validate
from .models import (
    ConsolidationOutcome,
    Finding,
    MemoryScope,
    PolicyDecision,
    ScrubbedText,
    TurnRef,
    from_iso,
    new_id,
    to_iso,
    utcnow,
)
from .retrieval import Retriever
from .store import MemoryStore

PREV_REPLY_MAX = 500
DEFAULT_IDLE_TIMEOUT_S = 10.0
_PROBE_RX = re.compile(r"(?i)^(draft|write|send|schedule|tell|show|find|book|what|when|who|how|which|where|why)\b")


@dataclass
class PreparedTurn:
    turn: TurnRef
    scrubbed: ScrubbedText
    ltm_block: str = ""
    notices: List[str] = field(default_factory=list)
    is_forget_only: bool = False
    kind: str = "setup"
    # B3: when a message mixes a forget clause with other clauses, only the other clauses are ingested, and they are
    # treated as stated just after the forget (so this turn's own tombstone does not fence them).
    ingest_text: Optional[str] = None
    ingest_turn: Optional[TurnRef] = None


@dataclass
class IngestJob:
    turn: TurnRef
    llm_safe_text: str
    prev_reply_llm_safe: str
    duplicate: bool = False


def new_turn_id(observed_at: datetime) -> str:
    return f"turn_{to_iso(observed_at)}_{os.urandom(2).hex()}"


class MemoryService:
    def __init__(self, store: MemoryStore, *, extractor: Optional[Extractor] = None, debug_events: bool = False,
                 test_hooks: bool = False, jsonl_path=None, scope_resolver=None):
        from . import resolve_memory_scope

        self.store = store
        self.sink = EventSink(store, debug_events=debug_events, jsonl_path=jsonl_path)
        self.retriever = Retriever(store, self.sink, debug_events=debug_events)
        self.extractor: Extractor = extractor or RuleExtractor()
        self.debug_events = debug_events
        self.test_hooks = test_hooks
        self.resolve_scope = scope_resolver or resolve_memory_scope
        self._locks: Dict[Tuple[int, str], asyncio.Lock] = {}
        self._state = threading.Lock()
        self._pending = 0
        self._pending_delayed = 0
        self._dup_delay_ms: Optional[int] = None
        self._tasks: Set["asyncio.Task[Any]"] = set()

    # ------------------------------------------------------------------ sync turn path

    def prepare_turn(self, text: str, source_kind: str, ingress_findings: Sequence[Finding] = (),
                     observed_at: Optional[datetime] = None) -> PreparedTurn:
        """P0 + forget + retrieval. No network I/O. Fails closed for memory, open for chat."""
        observed_at = observed_at or utcnow()
        scope = self.resolve_scope()
        trace = new_id("trc")
        try:
            turn = TurnRef(trace, new_turn_id(observed_at), scope, observed_at, self.store.epoch(scope), source_kind)
        except Exception:
            turn = TurnRef(trace, new_turn_id(observed_at), scope, observed_at, -1, source_kind)
            return PreparedTurn(turn, ScrubbedText("", []))
        try:
            return self._prepare(text, turn, ingress_findings)
        except Exception as exc:  # pragma: no cover - defensive
            try:
                self.sink.emit(scope, trace, "ingest", decision="ERROR", reason_codes=[type(exc).__name__])
            except Exception:
                pass
            return PreparedTurn(turn, ScrubbedText("", []))

    def _prepare(self, text: str, turn: TurnRef, ingress_findings: Sequence[Finding]) -> PreparedTurn:
        scope, trace = turn.scope, turn.trace_id
        emit = lambda *a, **k: self.sink.emit(scope, trace, *a, **k)  # noqa: E731
        fr = forget_mod.detect(privacy.scrub(text)[0].llm_safe) if turn.source_kind == "user_message" else None
        kind = "forget" if fr else ("probe" if text.rstrip().endswith("?") or _PROBE_RX.match(text.strip()) else "setup")
        emit("ingest", detail={"source_kind": turn.source_kind, "chars": len(text), "turn_id": turn.turn_id,
                               "kind": kind, "observed_at": turn.observed_iso, "epoch": turn.epoch})
        emit("ingress.scrub", decision="SCRUBBED" if ingress_findings else "CLEAN",
             detail={"detectors": counts(ingress_findings)})

        scrubbed, _raw_map = privacy.scrub(text)  # _raw_map stays local, then dropped
        del _raw_map
        emit("privacy.scrub", detail={"detectors": counts(scrubbed.findings)})

        notices: List[str] = []
        if ingress_findings:
            placeholders = sorted({f.placeholder or f"[SECRET:{f.kind}]" for f in ingress_findings})
            notices.append(f"A secret-like value in the latest message was replaced with {', '.join(placeholders)} "
                           "and was not stored.")
        elif any(f.cls in ("SECRET", "REGULATED_ID") for f in scrubbed.findings):
            notices.append("A secret-like or ID-like value in the latest message was not saved to long-term memory.")

        is_forget_only = False
        ingest_text: Optional[str] = None
        ingest_turn: Optional[TurnRef] = None
        if fr:
            emit("forget.detect", decision=fr.kind.upper(), detail={"kind": fr.kind, "clauses": fr.clause_indices})
            result = forget_mod.apply(self.store, self.sink, scope, fr, trace)
            notices.append(result.notice)
            rest = [c for i, c in enumerate(split_clauses(scrubbed.llm_safe)) if i not in fr.clause_indices]
            is_forget_only = all(c.rstrip().endswith("?") for c in rest)
            if not is_forget_only:
                ingest_text = " ".join(rest)
                if result.tombstone_at:
                    after = max(turn.observed_at, from_iso(result.tombstone_at) + timedelta(milliseconds=1))
                    ingest_turn = TurnRef(turn.trace_id, turn.turn_id, turn.scope, after, turn.epoch, turn.source_kind)

        block, _items = self.retriever.retrieve_block(scope, scrubbed.llm_safe, turn.source_kind, trace)
        return PreparedTurn(turn, scrubbed, block, notices, is_forget_only, kind, ingest_text, ingest_turn)

    # ------------------------------------------------------------------ async ingest

    def schedule_ingest(self, prepared: PreparedTurn, prev_reply: Optional[str] = None) -> None:
        if prepared.turn.source_kind != "user_message":  # D6: only user-authored turns
            return
        if prepared.is_forget_only or prepared.turn.epoch < 0:  # "forget X" is a command, not a fact
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        prev = privacy.scrub(privacy.ingress_scrub(prev_reply or "")[0])[0].llm_safe[:PREV_REPLY_MAX]
        job = IngestJob(prepared.ingest_turn or prepared.turn,
                        prepared.ingest_text if prepared.ingest_text is not None else prepared.scrubbed.llm_safe, prev)
        self._spawn(loop, job, 0)
        with self._state:
            dup_ms, self._dup_delay_ms = self._dup_delay_ms, None
        if dup_ms:
            # C14: a faithful stale duplicate (same TurnRef) that sleeps BEFORE taking the per-user lock.
            self._spawn(loop, IngestJob(job.turn, job.llm_safe_text, job.prev_reply_llm_safe, duplicate=True), dup_ms)

    def _spawn(self, loop: asyncio.AbstractEventLoop, job: IngestJob, delay_ms: int) -> None:
        with self._state:
            self._pending += 1
            if delay_ms:
                self._pending_delayed += 1
        task = loop.create_task(self._run_job(job, delay_ms))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _lock_for(self, user_id: str) -> asyncio.Lock:
        key = (id(asyncio.get_running_loop()), user_id)
        with self._state:
            lock = self._locks.get(key)
            if lock is None:
                lock = self._locks[key] = asyncio.Lock()
            return lock

    async def _run_job(self, job: IngestJob, delay_ms: int = 0) -> None:
        try:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000.0)
            async with self._lock_for(job.turn.scope.user_id):  # serialise per user, preserves order
                try:
                    await self.ingest(job)
                except Exception as exc:  # no retry loop in the prototype (avoids repeating baseline F-6)
                    self.sink.emit(job.turn.scope, job.turn.trace_id, "extract", decision="ERROR",
                                   reason_codes=[type(exc).__name__])
        finally:
            with self._state:
                self._pending -= 1
                if delay_ms:
                    self._pending_delayed -= 1

    async def ingest(self, job: IngestJob) -> None:
        turn = job.turn
        scope, trace = turn.scope, turn.trace_id
        emit = lambda *a, **k: self.sink.emit(scope, trace, *a, **k)  # noqa: E731
        existing_keys = self.store.slot_keys(scope)  # keys only, never values
        t0 = time.perf_counter()
        result = await self.extractor.extract(job.llm_safe_text, job.prev_reply_llm_safe, existing_keys,
                                              turn.observed_at)
        kept, dropped = validate(result.candidates, job.llm_safe_text)
        emit("extract", decision="ERROR" if result.error else "OK",
             reason_codes=[result.error] if result.error else [], detail={
                 "n_candidates": len(kept), "extractor_version": result.extractor_version,
                 "latency_ms": round((time.perf_counter() - t0) * 1000, 2), "duplicate": job.duplicate})
        for rep in report_clauses(job.llm_safe_text, kept, result.ignored):
            if rep["candidate_id"]:
                c = next(c for c in kept if c.candidate_id == rep["candidate_id"])
                emit("extract.clause", candidate_id=c.candidate_id, decision="CANDIDATE", safe_text=rep["clause"],
                     detail={"clause_index": rep["clause_index"], "label": vocab.label(c.predicate)})
            else:
                emit("extract.clause", decision="NO_CANDIDATE", reason_codes=[rep["reason"]], safe_text=rep["clause"],
                     detail={"clause_index": rep["clause_index"], "reason": rep["reason"]})
        for c, why in dropped:
            # Dropped candidates' free text is not trusted (B4): show the template sentence for known predicates only.
            known = vocab.is_storable(c.predicate) and not c.predicate.startswith("pref.custom:")
            emit("validate", candidate_id=c.candidate_id, decision="IGNORE", reason_codes=[why],
                 detail={"reason": why},
                 safe_text=policy.canonical_text(c, policy.assign_slot(c)) if known else None)

        for c in kept:
            verdict = privacy.classify(c, rerender=lambda c: vocab.render(c.predicate, c.value, c.object_entity))
            lbl = vocab.label(c.predicate)
            # Events show the same deterministic text that would be stored (B4), never extractor free text.
            shown = policy.canonical_text(c, policy.assign_slot(c))
            emit("privacy.classify", candidate_id=c.candidate_id, decision=verdict.action,
                 reason_codes=verdict.reasons,
                 detail={"sensitivity": verdict.sensitivity, "categories": verdict.categories,
                         "detectors": verdict.detector_types, "label": lbl},
                 safe_text=shown)
            d = policy.decide(c, verdict, turn.source_kind,
                              value_hmac=lambda k, x: self.store.value_hmac(scope, k, x),
                              source_turn_id=turn.turn_id, observed_at=turn.observed_at,
                              extractor_version=result.extractor_version)
            value_disp = None
            if d.record is not None:
                value_disp = vocab.display_value(d.record.slot.predicate, d.record.value_json)
            emit("policy", candidate_id=c.candidate_id, decision=d.kind.value, reason_codes=d.reasons,
                 detail={"label": lbl, "importance": d.importance, "importance_breakdown": d.importance_breakdown,
                         "confidence": d.confidence, "slot_key": d.slot.slot_key if d.slot else None,
                         "scores": {"importance": d.importance, "confidence": d.confidence}},
                 safe_text=shown,
                 dev_detail={"label_value": f"{lbl} = {value_disp}"} if value_disp else None)
            if d.kind != PolicyDecision.STORE or d.record is None:
                continue
            rec = d.record
            out = self.store.commit_candidate(turn, rec, keywords_for_row(rec.slot_key, rec.slot.predicate,
                                                                          rec.slot.subject))
            if out.kind == ConsolidationOutcome.FENCE_DROP:
                reason = out.reason_codes[0]
                refs = out.detail.get("refs", {})
                if reason == "TOMBSTONED":
                    self.store.scrub_job_events(scope, trace, c.candidate_id)  # leave no forgotten text behind
                emit("fence_drop", candidate_id=c.candidate_id, decision=reason, reason_codes=[reason],
                     detail={"slot_key": rec.slot_key, "refs": refs, "label": lbl, "duplicate": job.duplicate,
                             "reason": f"job observed_at {refs.get('job_observed_at')} ≤ tombstone "
                                       f"{refs.get('tombstone_at')}" if reason == "TOMBSTONED" else
                                       "epoch changed since the turn was received"})
                continue
            detail = dict(out.detail)
            detail.setdefault("scores", {"importance": rec.importance, "confidence": rec.confidence})
            detail["label"] = lbl
            detail["duplicate"] = job.duplicate
            emit("consolidate", candidate_id=c.candidate_id, memory_id=out.memory_id, decision=out.kind.value,
                 reason_codes=out.reason_codes, detail=detail, dev_detail=out.dev_detail,
                 safe_text=rec.canonical_text if out.kind != ConsolidationOutcome.DROP_STALE else None)

    # ------------------------------------------------------------------ idle / hooks / admin

    def pending(self, include_delayed: bool = True) -> int:
        with self._state:
            return self._pending if include_delayed else self._pending - self._pending_delayed

    async def await_idle(self, timeout: float = DEFAULT_IDLE_TIMEOUT_S, include_delayed: bool = True) -> bool:
        """C2: True once every job (incl. delayed duplicates unless excluded) has committed or fence-dropped."""
        deadline = time.monotonic() + timeout
        while self.pending(include_delayed) > 0:
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.02)
        return True

    def set_duplicate_next_job(self, delay_ms: int) -> None:
        if not self.test_hooks:
            raise PermissionError("test hooks disabled")
        with self._state:
            self._dup_delay_ms = int(delay_ms)

    def bump_epoch(self, scope: Optional[MemoryScope] = None) -> int:
        return self.store.bump_epoch(scope or self.resolve_scope())

    def forget_all(self, scope: Optional[MemoryScope] = None) -> Dict[str, Any]:
        return forget_mod.forget_all(self.store, self.sink, scope or self.resolve_scope())

    def list_traces(self, scope: Optional[MemoryScope] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """C1: newest first ``[{trace_id, ts, source_kind, kind, turn_id}]``."""
        scope = scope or self.resolve_scope()
        events = self.sink.stage_events(scope, "ingest")
        out = [{"trace_id": e["trace_id"], "ts": e["ts"], "source_kind": e["detail"].get("source_kind"),
                "kind": e["detail"].get("kind"), "turn_id": e["detail"].get("turn_id")} for e in events]
        return list(reversed(out))[: max(0, int(limit))]

    def sweep(self) -> List[str]:
        scope = self.resolve_scope()
        return self.store.sweep(on_expire=lambda mid: self.sink.emit(scope, None, "expire", memory_id=mid))
