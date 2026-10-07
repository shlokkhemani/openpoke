"""Shared helpers for the LTM unit suites."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from server.services.memory.models import (
    EXTRACTOR_VERSION_RULES,
    POLICY_VERSION,
    MemoryScope,
    NewRecord,
    SlotInfo,
    to_iso,
    utcnow,
)
from server.services.memory.store import MemoryStore

TEST_KEY = b"unit-test-hmac-key-not-secret-000"


class TempStoreCase(unittest.TestCase):
    """Gives each test a fresh ltm.db in a temp dir."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ltm-test-"))
        self.store = MemoryStore(self.tmp / "memory" / "ltm.db", hmac_key=TEST_KEY, test_mode=True)
        self.scope = MemoryScope("user-a")
        self.other = MemoryScope("user-b")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def make_record(store: MemoryStore, scope: MemoryScope, value: str, *, predicate="pref.favorite_programming_language",
                cardinality="single", observed_at=None, confidence=0.90, text=None) -> NewRecord:
    slot = SlotInfo("preference", "user", predicate, cardinality, f"user|{predicate}", "entity", False, ())
    canonical = value.lower()
    return NewRecord(
        slot=slot,
        value_json=f'"{canonical}"',
        value_hmac=store.value_hmac(scope, slot.slot_key, canonical),
        canonical_text=text or f"User's favorite programming language is {value}.",
        importance=0.75,
        confidence=confidence,
        sensitivity="low",
        pii_categories=[],
        source_kind="user_message",
        source_turn_id="turn_test",
        observed_at=observed_at or to_iso(utcnow()),
        expires_at=None,
        extractor_version=EXTRACTOR_VERSION_RULES,
        policy_version=POLICY_VERSION,
    )


def commit_text(store: MemoryStore, scope: MemoryScope, text: str, observed_at, n: int = 1, epoch=None):
    """ingress -> P0 -> RuleExtractor -> validate -> P1 -> policy -> fenced commit, for every STORE candidate."""
    from server.services.memory import policy, privacy
    from server.services.memory.consolidate import keywords_for_row
    from server.services.memory.extractor import RuleExtractor, validate
    from server.services.memory.models import TurnRef

    llm_safe = privacy.scrub(privacy.ingress_scrub(text)[0])[0].llm_safe
    kept, _ = validate(RuleExtractor().extract_sync(llm_safe, observed_at).candidates, llm_safe)
    turn = TurnRef(f"trc_{n}", f"turn_{n}", scope, observed_at, store.epoch(scope) if epoch is None else epoch,
                   "user_message")
    outs = []
    for c in kept:
        d = policy.decide(c, privacy.classify(c), "user_message",
                          value_hmac=lambda k, x: store.value_hmac(scope, k, x), source_turn_id=turn.turn_id,
                          observed_at=observed_at, extractor_version="rules-0.1")
        if d.kind.value == "STORE":
            rec = d.record
            outs.append(store.commit_candidate(turn, rec, keywords_for_row(rec.slot_key, rec.slot.predicate,
                                                                           rec.slot.subject)))
    return outs


SECRET = "sk-test-SYNTHETIC-12345"


class RecordingExtractor:
    """Wraps the RuleExtractor and records exactly what an extractor received (the extractor-capture sink)."""

    def __init__(self, gate=None):
        from server.services.memory.extractor import RuleExtractor

        self.inner = RuleExtractor()
        self.version = self.inner.version
        self.calls = []
        self.gate = gate  # optional asyncio.Event: blocks extraction (forget-before-write)

    async def extract(self, llm_safe_text, prev_reply_llm_safe, existing_keys, observed_at):
        self.calls.append({"text": llm_safe_text, "prev": prev_reply_llm_safe, "keys": list(existing_keys)})
        if self.gate is not None:
            await self.gate.wait()
        return await self.inner.extract(llm_safe_text, prev_reply_llm_safe, existing_keys, observed_at)


def make_service(store, scope, extractor=None, debug_events=True):
    from server.services.memory.service import MemoryService

    return MemoryService(store, extractor=extractor or RecordingExtractor(), debug_events=debug_events,
                         test_hooks=True, scope_resolver=lambda: scope)


def user_turn(service, raw_text, prev_reply=None):
    """What runtime.execute does with the flags on: ingress scrub first, then prepare_turn + schedule_ingest.
    Must be called inside a running event loop."""
    from server.services.memory.privacy import ingress_scrub

    text, findings = ingress_scrub(raw_text)
    prepared = service.prepare_turn(text, "user_message", findings)
    service.schedule_ingest(prepared, prev_reply)
    return prepared


def ltm_bytes(store) -> bytes:
    store.checkpoint_truncate()
    out = b""
    for suffix in ("", "-wal", "-shm"):
        p = store.db_path.parent / (store.db_path.name + suffix)
        if p.exists():
            out += p.read_bytes()
    return out


def all_sql_text(store) -> str:
    """Every column of memory_events, memories and every memories_fts* shadow table, as text."""
    import json as _json

    chunks = []
    with store.read() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            for row in conn.execute(f'SELECT * FROM "{t}"'):
                chunks.append(_json.dumps([x if not isinstance(x, bytes) else x.decode("latin-1") for x in row]))
    return "\n".join(chunks)
