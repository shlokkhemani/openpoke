"""Step 8 gate: slot-chain purge, tombstones, both race variants, forget grammar, byte canary."""

from __future__ import annotations

import unittest

from server.services.memory import forget
from server.services.memory.trace import assemble_turn_trace

from ._util import RecordingExtractor, TempStoreCase, all_sql_text, ltm_bytes, make_service, user_turn

MEET = "user|pref.meeting_time"
LANG = "user|pref.favorite_programming_language"
CANARIES = [b"User prefers meetings after 10 AM", b'{"after":"10:00"}', b'{"after": "10:00"}', b"after 10 AM"]


class ServiceCase(TempStoreCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        TempStoreCase.setUp(self)
        self.svc = make_service(self.store, self.scope)

    def events(self, trace_id, stage=None):
        ev = self.svc.sink.events(self.scope, trace_id)
        return [e for e in ev if stage is None or e["stage"] == stage]


class TestForgetPurge(ServiceCase):
    async def test_slot_chain_purged_and_tombstoned(self):
        user_turn(self.svc, "My favorite programming language is Python.")
        await self.svc.await_idle()
        user_turn(self.svc, "Actually, my favorite programming language is Rust.")
        await self.svc.await_idle()
        ids = [r["id"] for r in self.store.rows_in_slot(self.scope, LANG)]
        self.assertEqual(len(ids), 2)

        p = user_turn(self.svc, "Forget my favorite programming language.")
        self.assertTrue(p.is_forget_only)
        self.assertEqual(p.ltm_block, "")  # forget runs before the same turn's retrieval
        self.assertIn("Deleted 2 long-term memory item(s) about: favorite programming language.", p.notices)
        await self.svc.await_idle()

        rows = self.store.rows_in_slot(self.scope, LANG)
        self.assertEqual([(r["status"], r["canonical_text"], r["value_json"]) for r in rows],
                         [("deleted", None, None)] * 2)
        self.assertEqual(self.store.fts_memory_ids(self.scope), [])
        with self.store.read() as conn:
            texts = conn.execute("SELECT safe_text FROM memory_events WHERE memory_id IN (?,?)", ids).fetchall()
        self.assertTrue(texts and all(t[0] is None for t in texts))
        self.assertNotIn("Python", all_sql_text(self.store))
        self.assertNotIn("Rust", all_sql_text(self.store))
        tombs = sorted((t["scope"], t["slot_key"]) for t in self.store.tombstones(self.scope))
        self.assertEqual(tombs, [("slot", LANG), ("value", LANG), ("value", LANG)])
        (fa,) = self.events(p.turn.trace_id, "forget.apply")
        self.assertEqual((fa["decision"], fa["detail"]["count"]), ("DELETE", 2))

    async def test_new_statement_after_forget_is_stored(self):
        user_turn(self.svc, "I prefer meetings after 10 AM.")
        await self.svc.await_idle()
        user_turn(self.svc, "Forget my meeting preference.")
        user_turn(self.svc, "I prefer meetings after 9 AM.")
        await self.svc.await_idle()
        active = self.store.rows_in_slot(self.scope, MEET, ["active"])
        self.assertEqual([r["canonical_text"] for r in active], ["User prefers meetings after 9 AM."])


class TestRace(ServiceCase):
    async def test_stale_writer_fence_dropped(self):
        """Proof 4: the delayed duplicate of the turn-0 ingest job hits the tombstone and is dropped."""
        self.svc.set_duplicate_next_job(300)
        p0 = user_turn(self.svc, "I prefer meetings after 10 AM.")
        self.assertTrue(await self.svc.await_idle(include_delayed=False))  # first copy committed
        self.assertEqual(self.svc.pending(), 1)  # the stale duplicate is still sleeping
        self.assertEqual(len(self.store.rows_in_slot(self.scope, MEET, ["active"])), 1)

        p1 = user_turn(self.svc, "Forget my meeting preference.")
        rows_before_drop = self.store.rows_in_slot(self.scope, MEET)
        self.assertTrue(await self.svc.await_idle())  # duplicate ran through the real commit fence
        rows_after_drop = self.store.rows_in_slot(self.scope, MEET)

        (fd,) = self.events(p0.turn.trace_id, "fence_drop")
        self.assertEqual(fd["decision"], "TOMBSTONED")
        refs = fd["detail"]["refs"]
        self.assertLess(refs["job_observed_at"], refs["tombstone_at"])
        self.assertEqual(refs["job_observed_at"], p0.turn.observed_iso)
        self.assertTrue(fd["detail"]["duplicate"])
        self.assertEqual([(r["id"], r["status"]) for r in rows_after_drop],
                         [(r["id"], r["status"]) for r in rows_before_drop])
        self.assertEqual([r["status"] for r in rows_after_drop], ["deleted"])

        probe = user_turn(self.svc, "When do I prefer meetings?")
        self.assertEqual(probe.ltm_block, "")
        t = assemble_turn_trace(self.svc.sink, self.scope, p0.turn.trace_id)
        self.assertIn("fence_drop", t["path"])
        fence_rows = [o for o in t["outcomes"] if o["result"] == "FENCE_DROP"]
        self.assertEqual(len(fence_rows), 1)
        self.assertEqual(fence_rows[0]["reason"], "TOMBSTONED")
        self.assertEqual([p["node"] for p in t["pipeline"] if p["stage"] == "fence_drop"], ["fence_drop"])
        self.assertEqual(assemble_turn_trace(self.svc.sink, self.scope, p1.turn.trace_id)["path"][:4],
                         ["conversation", "ingress_scrub", "privacy", "delete"])

    async def test_forget_before_write_fence_dropped(self):
        """D27: the forget arrives while the ONLY ingest job is still in flight; no row exists yet."""
        import asyncio

        gate = asyncio.Event()
        self.svc = make_service(self.store, self.scope, extractor=RecordingExtractor(gate=gate))
        p0 = user_turn(self.svc, "I prefer meetings after 10 AM.")
        await asyncio.sleep(0.05)
        self.assertEqual(self.store.rows_in_slot(self.scope, MEET), [])

        p1 = user_turn(self.svc, "Forget my meeting preference.")
        self.assertIn("No stored memory about meeting time preference yet; it will not be remembered.", p1.notices)
        self.assertEqual([(t["scope"], t["slot_key"]) for t in self.store.tombstones(self.scope)], [("slot", MEET)])

        gate.set()
        self.assertTrue(await self.svc.await_idle())
        (fd,) = self.events(p0.turn.trace_id, "fence_drop")
        self.assertEqual(fd["decision"], "TOMBSTONED")
        self.assertEqual(self.store.rows_in_slot(self.scope, MEET), [])

    async def test_clear_chat_epoch_fences_in_flight_job(self):
        import asyncio

        gate = asyncio.Event()
        self.svc = make_service(self.store, self.scope, extractor=RecordingExtractor(gate=gate))
        p0 = user_turn(self.svc, "I prefer meetings after 10 AM.")
        self.svc.bump_epoch()  # DELETE /chat/history with LTM on
        gate.set()
        await self.svc.await_idle()
        (fd,) = self.events(p0.turn.trace_id, "fence_drop")
        self.assertEqual(fd["decision"], "EPOCH_CHANGED")


class TestForgetGrammar(ServiceCase):
    def test_reminders_and_non_memory_deletes_are_not_forgets(self):
        self.assertIsNone(forget.detect("Don't forget to email Bob"))
        self.assertIsNone(forget.detect("don't forget my dentist appointment"))
        self.assertIsNone(forget.detect("Delete the email from Bob"))
        self.assertEqual(forget.detect("Forget my meeting preference.").kind, "targeted")
        self.assertEqual(forget.detect("Please delete what you remember about my manager").kind, "targeted")
        self.assertEqual(forget.detect("Forget everything about me").kind, "all")

    async def test_dont_forget_is_not_a_forget(self):
        user_turn(self.svc, "I prefer meetings after 10 AM.")
        await self.svc.await_idle()
        p = user_turn(self.svc, "Don't forget to email Bob about meetings")
        self.assertFalse(p.is_forget_only)
        self.assertEqual(len(self.store.rows_in_slot(self.scope, MEET, ["active"])), 1)
        self.assertEqual(self.store.tombstones(self.scope), [])

    async def test_ambiguous_forget_deletes_nothing(self):
        user_turn(self.svc, "I prefer concise emails.")
        user_turn(self.svc, "Never email Bob without asking me.")
        await self.svc.await_idle()
        before = [(r["id"], r["status"]) for r in self.store.all_rows(self.scope)]
        p = user_turn(self.svc, "Forget what I said about email.")
        self.assertTrue(any(n.startswith("Ambiguous forget request. Ask which one:") for n in p.notices))
        self.assertEqual([(r["id"], r["status"]) for r in self.store.all_rows(self.scope)], before)
        self.assertEqual(self.store.tombstones(self.scope), [])

    async def test_forget_all_is_api_only_from_chat(self):
        user_turn(self.svc, "I prefer meetings after 10 AM.")
        await self.svc.await_idle()
        p = user_turn(self.svc, "Forget everything about me.")
        self.assertTrue(any("nothing was deleted yet" in n for n in p.notices))
        self.assertEqual(len(self.store.rows_in_slot(self.scope, MEET, ["active"])), 1)
        self.svc.forget_all()
        self.assertEqual([r["status"] for r in self.store.all_rows(self.scope)], ["deleted"])


class TestByteCanary(ServiceCase):
    async def test_bytes_absent_from_ltm_db_after_checkpoint(self):
        self.svc.set_duplicate_next_job(200)
        user_turn(self.svc, "I prefer meetings after 10 AM.")
        await self.svc.await_idle(include_delayed=False)
        user_turn(self.svc, "When should I schedule a meeting?")  # renders the memory into a retrieve.select block
        before = ltm_bytes(self.store)
        self.assertIn(CANARIES[0], before)  # sanity: the canary really was on disk
        user_turn(self.svc, "Forget my meeting preference.")
        await self.svc.await_idle()  # the stale duplicate writes its own events, then is fence-dropped
        after = ltm_bytes(self.store)
        for canary in CANARIES:
            self.assertNotIn(canary, after, canary)


if __name__ == "__main__":
    unittest.main()


class TestReviewM1FalseForget(ServiceCase):
    """Review M1 / LTM_BLOCKERS.md B3: ordinary sentences containing "forget" must not delete or tombstone."""

    async def test_i_forget_question_keeps_preference(self):
        user_turn(self.svc, "I prefer meetings after 10 AM.")
        await self.svc.await_idle()
        p = user_turn(self.svc, "I forget what time my meeting with Dana is, can you check my calendar?")
        await self.svc.await_idle()
        self.assertEqual(len(self.store.rows_in_slot(self.scope, MEET, ["active"])), 1)
        self.assertEqual(self.store.tombstones(self.scope), [])
        self.assertFalse(any("Deleted" in n or "will not be remembered" in n for n in p.notices))

    async def test_i_always_forget_plus_fact_is_stored(self):
        p = user_turn(self.svc, "I always forget my schedule. I prefer meetings after 2 PM.")
        await self.svc.await_idle()
        self.assertEqual([r["canonical_text"] for r in self.store.rows_in_slot(self.scope, MEET, ["active"])],
                         ["User prefers meetings after 2 PM."])
        self.assertEqual(self.store.tombstones(self.scope), [])
        self.assertEqual(self.events(p.turn.trace_id, "fence_drop"), [])

    async def test_explicit_forget_still_deletes(self):
        user_turn(self.svc, "I prefer meetings after 10 AM.")
        await self.svc.await_idle()
        p = user_turn(self.svc, "Forget my meeting preference.")
        self.assertTrue(p.is_forget_only)
        self.assertEqual([r["status"] for r in self.store.rows_in_slot(self.scope, MEET)], ["deleted"])

    async def test_forget_clause_does_not_tombstone_new_fact_in_same_message(self):
        user_turn(self.svc, "I prefer meetings after 10 AM.")
        await self.svc.await_idle()
        p = user_turn(self.svc, "Forget my meeting preference. I prefer meetings after 2 PM.")
        self.assertFalse(p.is_forget_only)
        await self.svc.await_idle()
        rows = self.store.rows_in_slot(self.scope, MEET)
        self.assertEqual(sorted((r["status"], r["canonical_text"]) for r in rows),
                         [("active", "User prefers meetings after 2 PM."), ("deleted", None)])
        self.assertEqual(self.events(p.turn.trace_id, "fence_drop"), [])

    def test_grammar_negatives_and_positives(self):
        for text in ("I forget what time my meeting with Dana is", "I always forget my schedule.",
                     "I often forgot my password", "I don't remember my dentist's name", "Forget it.",
                     "Don't forget to email Bob", "don't forget my dentist appointment", "Delete the email from Bob"):
            self.assertIsNone(forget.detect(text), text)
        for text, kind in (("Forget my meeting preference.", "targeted"), ("Please forget my manager.", "targeted"),
                           ("Forget what I said about email.", "targeted"),
                           ("I want you to forget my meeting preference.", "targeted"),
                           ("Please delete what you remember about my manager", "targeted"),
                           ("Forget everything about me", "all")):
            fr = forget.detect(text)
            self.assertIsNotNone(fr, text)
            self.assertEqual(fr.kind, kind, text)


class TestReviewM2DebugEventResidue(ServiceCase):
    """Review M2: with debug events on, forgotten values and ignored clause text must not linger in ltm.db."""

    def event_text(self) -> str:
        with self.store.read() as conn:
            return "\n".join(f"{r[0] or ''} {r[1]}" for r in conn.execute(
                "SELECT safe_text, detail_json FROM memory_events")).lower()

    async def test_forgotten_value_tokens_absent(self):
        user_turn(self.svc, "I prefer meetings after 10 AM.")
        await self.svc.await_idle()
        user_turn(self.svc, "When should I schedule a meeting? Is 10 AM ok?")
        await self.svc.await_idle()
        self.assertIn("10 am", self.event_text())  # sanity: the value really was in debug events
        user_turn(self.svc, "Forget my meeting preference.")
        await self.svc.await_idle()
        blob = ltm_bytes(self.store)
        for canary in CANARIES + [b'"10:00"', b"10 AM"]:
            self.assertNotIn(canary, blob, canary)
        text = self.event_text()  # bare HH:MM checked in content columns only (timestamps contain it legitimately)
        for needle in ("10:00", "10 am", "after 10"):
            self.assertNotIn(needle, text, needle)

    async def test_forgotten_entity_absent_case_insensitive(self):
        user_turn(self.svc, "My favorite programming language is Haskell.")
        await self.svc.await_idle()
        user_turn(self.svc, "Is Haskell good for compilers?")
        await self.svc.await_idle()
        user_turn(self.svc, "Forget my favorite programming language.")
        await self.svc.await_idle()
        self.assertNotIn(b"haskell", ltm_bytes(self.store).lower())

    async def test_query_terms_not_stored_in_events(self):
        p = user_turn(self.svc, "What's my favorite programming language, Haskell?")
        (q,) = self.events(p.turn.trace_id, "retrieve.query")
        self.assertNotIn("terms", q["detail"])
        self.assertNotIn("entities", q["detail"])
        self.assertEqual(q["detail"]["n_terms"] > 0, True)

    async def test_ignored_clause_text_cleared_by_7_day_retention(self):
        from datetime import datetime, timedelta, timezone

        user_turn(self.svc, "I prefer meetings after 10 AM. I'm eating a turkey sandwich right now.")
        await self.svc.await_idle()
        self.assertIn("turkey", self.event_text())  # retained for the debug view (D25), not as a memory
        self.assertEqual([r["canonical_text"] for r in self.store.all_rows(self.scope)],
                         ["User prefers meetings after 10 AM."])
        self.store.sweep(now=datetime.now(timezone.utc) + timedelta(days=6))
        self.assertIn("turkey", self.event_text())
        self.store.sweep(now=datetime.now(timezone.utc) + timedelta(days=8))
        self.assertNotIn("turkey", self.event_text())
        self.assertNotIn(b"turkey", ltm_bytes(self.store))
        self.assertEqual(len(self.store.rows_in_slot(self.scope, MEET, ["active"])), 1)  # memory itself unaffected
