"""Step 1 gate: schema, invariants, same-transaction FTS, two-scope isolation."""

from __future__ import annotations

import os
import sqlite3
import stat
import unittest

from server.services.memory.store import MemoryStore

from ._util import TempStoreCase, make_record


class TestSchema(TempStoreCase):
    def test_schema_creates(self):
        with self.store.read() as conn:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            secure = conn.execute("PRAGMA secure_delete").fetchone()[0]
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        for name in ("memory_users", "memories", "memories_fts", "memory_tombstones", "memory_events",
                     "ux_one_active_single_slot", "ux_active_multi_value", "ix_events_trace"):
            self.assertIn(name, names)
        self.assertEqual(journal, "wal")
        self.assertEqual(secure, 1)  # connection-scoped pragma applied per connection (C9)
        self.assertEqual(fk, 1)

    def test_schema_is_idempotent(self):
        MemoryStore(self.store.db_path, hmac_key=b"k")  # reopening must not fail
        MemoryStore(self.store.db_path, hmac_key=b"k")

    def test_direct_second_active_insert_raises(self):
        a = make_record(self.store, self.scope, "Python")
        b = make_record(self.store, self.scope, "Rust")
        with self.store.write() as conn:
            self.store.insert_row(conn, self.scope, a, status="active")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.write() as conn:
                self.store.insert_row(conn, self.scope, b, status="active")
        active = self.store.rows_in_slot(self.scope, a.slot_key, ["active"])
        self.assertEqual(len(active), 1)

    def test_multi_slot_rejects_duplicate_active_value(self):
        a = make_record(self.store, self.scope, "thai", predicate="pref.likes", cardinality="multi")
        b = make_record(self.store, self.scope, "sushi", predicate="pref.likes", cardinality="multi")
        with self.store.write() as conn:
            self.store.insert_row(conn, self.scope, a, status="active")
            self.store.insert_row(conn, self.scope, b, status="active")  # different value: allowed
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.write() as conn:
                self.store.insert_row(conn, self.scope, a, status="active")

    def test_deleted_with_content_violates_check(self):
        rec = make_record(self.store, self.scope, "Python")
        with self.store.write() as conn:
            mem_id = self.store.insert_row(conn, self.scope, rec, status="active")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.write() as conn:
                conn.execute("UPDATE memories SET status='deleted' WHERE id=?", (mem_id,))

    def test_fts_row_written_in_same_transaction(self):
        rec = make_record(self.store, self.scope, "Python")
        with self.assertRaises(RuntimeError):
            with self.store.write() as conn:
                mem_id = self.store.insert_row(conn, self.scope, rec, status="active")
                self.store.index_row(conn, self.scope, mem_id, rec.canonical_text, "programming language")
                raise RuntimeError("abort after both writes")
        self.assertEqual(self.store.all_rows(self.scope), [])
        self.assertEqual(self.store.fts_memory_ids(self.scope), [])

        with self.store.write() as conn:
            mem_id = self.store.insert_row(conn, self.scope, rec, status="active")
            self.store.index_row(conn, self.scope, mem_id, rec.canonical_text, "programming language")
        self.assertEqual(self.store.fts_memory_ids(self.scope), [mem_id])

    def test_hmac_key_file_mode_0600(self):
        os.environ.pop("OPENPOKE_LTM_HMAC_KEY", None)
        store = MemoryStore(self.tmp / "k" / "ltm.db")
        h1 = store.value_hmac(self.scope, "user|x", "v")
        key_path = self.tmp / "k" / ".hmac_key"
        self.assertTrue(key_path.exists())
        self.assertEqual(stat.S_IMODE(key_path.stat().st_mode), 0o600)
        self.assertEqual(len(key_path.read_bytes()), 32)
        # Reopen reuses the same key, so tombstone HMACs stay comparable across restarts.
        self.assertEqual(MemoryStore(self.tmp / "k" / "ltm.db").value_hmac(self.scope, "user|x", "v"), h1)


class TestIsolation(TempStoreCase):
    def _seed(self, scope, value):
        rec = make_record(self.store, scope, value)
        with self.store.write() as conn:
            mem_id = self.store.insert_row(conn, scope, rec, status="active")
            self.store.index_row(conn, scope, mem_id, rec.canonical_text, "programming language")
        return mem_id, rec

    def test_read_isolation(self):
        a_id, _ = self._seed(self.scope, "Python")
        b_id, _ = self._seed(self.other, "Rust")
        self.assertEqual([r["id"] for r in self.store.all_rows(self.scope)], [a_id])
        self.assertEqual([r["id"] for r in self.store.all_rows(self.other)], [b_id])
        self.assertIsNone(self.store.get_memory(self.scope, b_id))
        self.assertEqual(self.store.fts_memory_ids(self.scope), [a_id])
        # Same slot key in both scopes is fine: the unique index is per user.
        self.assertEqual(len(self.store.rows_in_slot(self.other, "user|pref.favorite_programming_language")), 1)

    def test_delete_isolation(self):
        a_id, rec = self._seed(self.scope, "Python")
        b_id, _ = self._seed(self.other, "Rust")
        out = self.store.purge_slot(self.scope, rec.slot_key, reason="user_forget")
        self.assertEqual(out["deleted_ids"], [a_id])
        a = self.store.get_memory(self.scope, a_id)
        self.assertEqual(a["status"], "deleted")
        self.assertIsNone(a["canonical_text"])
        self.assertIsNone(a["value_json"])
        self.assertEqual(self.store.fts_memory_ids(self.scope), [])
        b = self.store.get_memory(self.other, b_id)
        self.assertEqual(b["status"], "active")
        self.assertEqual(self.store.fts_memory_ids(self.other), [b_id])
        self.assertEqual(self.store.tombstones(self.other), [])
        kinds = sorted(t["scope"] for t in self.store.tombstones(self.scope))
        self.assertEqual(kinds, ["slot", "value"])

    def test_forget_all_isolation(self):
        self._seed(self.scope, "Python")
        b_id, _ = self._seed(self.other, "Rust")
        self.store.forget_all(self.scope)
        self.assertTrue(all(r["status"] == "deleted" for r in self.store.all_rows(self.scope)))
        self.assertEqual(self.store.get_memory(self.other, b_id)["status"], "active")
        self.assertEqual(self.store.epoch(self.scope), 1)
        self.assertEqual(self.store.epoch(self.other), 0)

    def test_epoch_isolation(self):
        self.assertEqual(self.store.epoch(self.scope), 0)
        self.assertEqual(self.store.bump_epoch(self.scope), 1)
        self.assertEqual(self.store.bump_epoch(self.scope), 2)
        self.assertEqual(self.store.epoch(self.other), 0)

    def test_empty_slot_tombstone(self):
        out = self.store.purge_slot(self.scope, "user|pref.meeting_time", reason="user_forget")
        self.assertEqual(out["deleted_ids"], [])
        tombs = self.store.tombstones(self.scope)
        self.assertEqual([(t["scope"], t["slot_key"], t["value_hmac"]) for t in tombs],
                         [("slot", "user|pref.meeting_time", None)])


if __name__ == "__main__":
    unittest.main()
