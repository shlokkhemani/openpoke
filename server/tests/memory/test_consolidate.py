"""Step 6 gate: INSERT / MERGE / SUPERSEDE / CONTEST / DROP_STALE, out-of-order, fence, supersede edge."""

from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from server.services.memory import policy, privacy, vocab
from server.services.memory.consolidate import keywords_for_row
from server.services.memory.events import EventSink
from server.services.memory.extractor import RuleExtractor, validate
from server.services.memory.models import TurnRef
from server.services.memory.trace import memory_state_snapshot

from ._util import TempStoreCase

T0 = datetime(2026, 10, 7, 15, 0, 0, tzinfo=timezone.utc)
ONE_ACTIVE_SQL = ("SELECT slot_key, COUNT(*) FROM memories WHERE user_id=? AND status='active' AND cardinality='single'"
                  " GROUP BY slot_key HAVING COUNT(*) > 1")


class ConsolidateCase(TempStoreCase):
    def turn(self, observed_at, epoch=None, n=1):
        return TurnRef(f"trc_{n}", f"turn_{n}", self.scope, observed_at,
                       self.store.epoch(self.scope) if epoch is None else epoch, "user_message")

    def record(self, text, observed_at):
        llm_safe = privacy.scrub(privacy.ingress_scrub(text)[0])[0].llm_safe
        (c,), _ = validate(RuleExtractor().extract_sync(llm_safe, observed_at).candidates, llm_safe)
        v = privacy.classify(c)
        d = policy.decide(c, v, "user_message", value_hmac=lambda k, x: self.store.value_hmac(self.scope, k, x),
                          source_turn_id="turn_x", observed_at=observed_at, extractor_version="rules-0.1")
        self.assertEqual(d.kind.value, "STORE")
        return d.record

    def commit(self, text, observed_at, n=1, epoch=None):
        rec = self.record(text, observed_at)
        kw = keywords_for_row(rec.slot_key, rec.slot.predicate, rec.slot.subject)
        return self.store.commit_candidate(self.turn(observed_at, epoch, n), rec, kw)

    def active(self, slot_key):
        return self.store.rows_in_slot(self.scope, slot_key, ["active"])

    def assert_one_active_invariant(self):
        with self.store.read() as conn:
            self.assertEqual(conn.execute(ONE_ACTIVE_SQL, (self.scope.user_id,)).fetchall(), [])


LANG = "user|pref.favorite_programming_language"
MEET = "user|pref.meeting_time"


class TestConflict(ConsolidateCase):
    def test_exactly_one_active_per_single_slot(self):
        a = self.commit("My favorite programming language is Python.", T0, n=1)
        self.assertEqual(a.kind.value, "INSERT")
        self.assert_one_active_invariant()
        b = self.commit("Actually, my favorite programming language is Rust.", T0 + timedelta(seconds=5), n=2)
        self.assertEqual(b.kind.value, "SUPERSEDE")
        self.assertEqual(b.old_id, a.memory_id)
        self.assert_one_active_invariant()

        python = self.store.get_memory(self.scope, a.memory_id)
        rust = self.store.get_memory(self.scope, b.memory_id)
        self.assertEqual((python["status"], python["superseded_by_id"]), ("superseded", rust["id"]))
        self.assertEqual((rust["status"], rust["supersedes_id"]), ("active", python["id"]))
        self.assertEqual(rust["canonical_text"], "User's favorite programming language is Rust.")
        self.assertEqual([r["id"] for r in self.active(LANG)], [rust["id"]])
        # FTS holds only retrievable rows.
        self.assertEqual(self.store.fts_memory_ids(self.scope), [rust["id"]])
        # The DB invariant is the backstop: a direct second active insert is unrepresentable.
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.write() as conn:
                self.store.insert_row(conn, self.scope, self.record("My favorite programming language is Go.", T0),
                                      status="active")

    def test_supersede_emits_edge(self):
        a = self.commit("My favorite programming language is Python.", T0, n=1)
        b = self.commit("Actually, my favorite programming language is Rust.", T0 + timedelta(seconds=5), n=2)
        self.assertEqual(b.detail["refs"]["old_id"], a.memory_id)
        self.assertEqual(b.reason_codes, ["SAME_SLOT_DIFFERENT_VALUE", "NEWER_EXPLICIT"])
        self.assertIn("Rust replaces Python", b.dev_detail["reason"])
        snap = memory_state_snapshot(self.store, EventSink(self.store), self.scope)
        self.assertEqual(snap["edges"], [{"from": a.memory_id, "to": b.memory_id, "kind": "superseded_by"}])
        self.assertEqual({m["display"]: m["status"] for m in snap["memories"]}, {"Python": "superseded", "Rust": "active"})

    def test_out_of_order_commit_leaves_rust_active(self):
        # Turn 2 (Rust, said later) commits BEFORE turn 1 (Python, said earlier).
        b = self.commit("Actually, my favorite programming language is Rust.", T0 + timedelta(seconds=5), n=2)
        a = self.commit("My favorite programming language is Python.", T0, n=1)
        self.assertEqual((b.kind.value, a.kind.value), ("INSERT", "DROP_STALE"))
        self.assertEqual(a.reason_codes, ["OLDER_STATEMENT"])
        rows = self.store.rows_in_slot(self.scope, LANG)
        self.assertEqual([(r["canonical_text"], r["status"]) for r in rows],
                         [("User's favorite programming language is Rust.", "active")])


class TestOutcomes(ConsolidateCase):
    def test_merge_reinforces_without_new_row(self):
        a = self.commit("I prefer meetings after 10 AM.", T0)
        m = self.commit("I prefer meetings after 10 AM.", T0 + timedelta(days=1))
        self.assertEqual((m.kind.value, m.memory_id), ("MERGE", a.memory_id))
        (row,) = self.store.rows_in_slot(self.scope, MEET)
        self.assertEqual((row["reinforcement_count"], row["confidence"], row["version"]), (1, 0.95, 2))
        self.assertTrue(row["last_confirmed_at"].startswith("2026-10-08"))

    def test_hedged_newer_value_contests(self):
        a = self.commit("I prefer meetings after 10 AM.", T0)
        c = self.commit("I think maybe afternoons are better for meetings?", T0 + timedelta(days=1))
        self.assertEqual(c.kind.value, "CONTEST")
        rows = {r["id"]: r for r in self.store.rows_in_slot(self.scope, MEET)}
        self.assertEqual(rows[a.memory_id]["status"], "active")
        self.assertEqual((rows[c.memory_id]["status"], rows[c.memory_id]["contests_id"]), ("contested", a.memory_id))
        self.assertEqual(set(self.store.fts_memory_ids(self.scope)), {a.memory_id, c.memory_id})
        # An explicit later statement resolves the contest.
        s = self.commit("Actually I prefer meetings after 1 PM now.", T0 + timedelta(days=2))
        self.assertEqual(s.kind.value, "SUPERSEDE")
        self.assertEqual(s.detail["refs"]["resolved_contested"], [c.memory_id])
        statuses = sorted(r["status"] for r in self.store.rows_in_slot(self.scope, MEET))
        self.assertEqual(statuses, ["active", "superseded", "superseded"])
        self.assertEqual(self.store.fts_memory_ids(self.scope), [s.memory_id])
        self.assert_one_active_invariant()

    def test_multi_slot_inserts_and_merges(self):
        a = self.commit("Never email Bob without asking me.", T0)
        b = self.commit("Never email Carol without asking me.", T0 + timedelta(seconds=1))
        c = self.commit("Never email Bob without asking me.", T0 + timedelta(seconds=2))
        self.assertEqual([a.kind.value, b.kind.value, c.kind.value], ["INSERT", "INSERT", "MERGE"])
        self.assertEqual(c.memory_id, a.memory_id)


class TestFence(ConsolidateCase):
    def test_tombstone_fences_older_statement_only(self):
        self.store.purge_slot(self.scope, MEET, reason="user_forget")
        dropped = self.commit("I prefer meetings after 10 AM.", T0 - timedelta(minutes=1))
        self.assertEqual((dropped.kind.value, dropped.reason_codes), ("FENCE_DROP", ["TOMBSTONED"]))
        self.assertEqual(set(dropped.detail["refs"]), {"job_observed_at", "tombstone_at"})
        self.assertEqual(self.store.rows_in_slot(self.scope, MEET), [])
        # A brand-new statement after the forget is stored normally (the user re-stated it).
        later = datetime.now(timezone.utc) + timedelta(seconds=1)
        self.assertEqual(self.commit("I prefer meetings after 9 AM.", later).kind.value, "INSERT")

    def test_epoch_change_fences(self):
        out = self.commit("I prefer meetings after 10 AM.", T0, epoch=0)
        self.assertEqual(out.kind.value, "INSERT")
        self.store.bump_epoch(self.scope)
        stale = self.commit("I prefer meetings after 11 AM.", T0 + timedelta(seconds=1), epoch=0)
        self.assertEqual((stale.kind.value, stale.reason_codes), ("FENCE_DROP", ["EPOCH_CHANGED"]))
        self.assertEqual(len(self.store.rows_in_slot(self.scope, MEET)), 1)

    def test_other_users_tombstones_do_not_fence(self):
        self.store.purge_slot(self.other, MEET, reason="user_forget")
        self.assertEqual(self.commit("I prefer meetings after 10 AM.", T0).kind.value, "INSERT")


if __name__ == "__main__":
    unittest.main()
