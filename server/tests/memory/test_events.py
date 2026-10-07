"""Step 3 gate: event sink, REJECT hygiene, trace skeleton, leak guard."""

from __future__ import annotations

import json
import unittest

from server.services.memory.events import EventSink
from server.services.memory.trace import (
    LTM_NODES,
    LeakError,
    assemble_turn_trace,
    leak_guard,
    memory_state_snapshot,
)

from ._util import TempStoreCase

SECRET = "sk-test-SYNTHETIC-12345"


class TestEvents(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.sink = EventSink(self.store, debug_events=True)

    def test_emit_and_read_by_trace_id(self):
        self.sink.emit(self.scope, "trc_1", "ingest", detail={"source_kind": "user_message", "chars": 10})
        self.sink.emit(self.scope, "trc_1", "privacy.scrub", detail={"detectors": []})
        self.sink.emit(self.scope, "trc_2", "ingest", detail={"source_kind": "user_message"})
        self.sink.emit(self.other, "trc_1", "ingest", detail={})  # other user, same trace id
        ev = self.sink.events(self.scope, "trc_1")
        self.assertEqual([e["stage"] for e in ev], ["ingest", "privacy.scrub"])
        self.assertEqual(ev[0]["detail"]["chars"], 10)
        self.assertEqual(len(self.sink.events(self.other, "trc_1")), 1)

    def test_unknown_stage_rejected(self):
        with self.assertRaises(ValueError):
            self.sink.emit(self.scope, "t", "made.up")

    def test_reject_events_carry_no_value_length_or_offset(self):
        self.sink.emit(self.scope, "trc_r", "policy", candidate_id="c2", decision="REJECT",
                       reason_codes=["SECRET_API_KEY"],
                       detail={"detectors": [{"type": "API_KEY", "count": 1}], "value": "[SECRET:API_KEY]",
                               "length": 23, "offset": 19, "start": 19, "end": 42},
                       safe_text="User's API key is [SECRET:API_KEY].",
                       dev_detail={"display": "[SECRET:API_KEY]"})
        (e,) = self.sink.events(self.scope, "trc_r")
        self.assertIsNone(e["safe_text"])
        self.assertEqual(e["detail"], {"detectors": [{"type": "API_KEY", "count": 1}]})
        self.assertEqual(e["reason_codes"], ["SECRET_API_KEY"])

    def test_event_backstop_redacts_prohibited_value(self):
        self.sink.emit(self.scope, "trc_x", "extract.clause", decision="NO_CANDIDATE",
                       detail={"oops": SECRET}, safe_text=f"key {SECRET}")
        (e,) = self.sink.events(self.scope, "trc_x")
        self.assertIsNone(e["safe_text"])
        self.assertIn("EGRESS_VIOLATION", e["reason_codes"])
        with self.store.read() as conn:
            dump = json.dumps([dict(r) for r in conn.execute("SELECT * FROM memory_events")])
        self.assertNotIn(SECRET, dump)

    def test_safe_text_and_dev_detail_only_in_debug_mode(self):
        quiet = EventSink(self.store, debug_events=False)
        quiet.emit(self.scope, "trc_q", "consolidate", decision="INSERT", safe_text="User prefers X.",
                   detail={"slot_key": "user|pref.x"}, dev_detail={"display": "X"})
        (e,) = quiet.events(self.scope, "trc_q")
        self.assertIsNone(e["safe_text"])
        self.assertEqual(e["detail"], {"slot_key": "user|pref.x"})


class TestTrace(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.sink = EventSink(self.store, debug_events=True)

    def test_leak_guard_raises_on_injected_secret(self):
        with self.assertRaises(LeakError) as ctx:
            leak_guard({"pipeline": [{"input_safe": f"My test API key is {SECRET}."}]})
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertEqual(leak_guard({"ok": "My test API key is [SECRET:API_KEY]."}),
                         {"ok": "My test API key is [SECRET:API_KEY]."})

    def test_turn_trace_path_and_outcomes(self):
        e = lambda *a, **k: self.sink.emit(self.scope, "trc_t", *a, **k)
        e("ingest", detail={"source_kind": "user_message", "turn_id": "turn_1", "kind": "setup"})
        e("ingress.scrub", decision="CLEAN", detail={"detectors": []})
        e("privacy.scrub", detail={"detectors": []})
        e("extract", decision="OK", detail={"n_candidates": 1})
        e("extract.clause", candidate_id="c1", decision="CANDIDATE", safe_text="I prefer meetings after 10 AM.",
          detail={"clause_index": 0})
        e("extract.clause", decision="NO_CANDIDATE", reason_codes=["TRANSIENT_STATE"],
          safe_text="I'm eating a turkey sandwich right now.", detail={"clause_index": 1})
        e("policy", candidate_id="c1", decision="STORE", detail={"label": "meeting time preference", "importance": 0.8})
        e("consolidate", candidate_id="c1", memory_id="mem_1", decision="INSERT", detail={"slot_key": "user|pref.meeting_time"})
        t = assemble_turn_trace(self.sink, self.scope, "trc_t")
        self.assertEqual(t["path"], ["conversation", "ingress_scrub", "privacy", "extract", "ignore", "policy",
                                     "consolidate", "store"])
        self.assertTrue(set(t["path"]) <= set(LTM_NODES))
        self.assertTrue({p["node"] for p in t["pipeline"]} <= set(LTM_NODES))
        self.assertEqual([(o["decision"], o["result"]) for o in t["outcomes"]],
                         [("STORE", "INSERT"), ("IGNORE", "NO_CANDIDATE")])
        self.assertEqual(t["outcomes"][1]["label"], "eating a turkey sandwich right now")
        self.assertEqual(t["outcomes"][1]["reason"], "TRANSIENT_STATE")
        self.assertIsNone(t["retrieval"])

    def test_empty_state_snapshot(self):
        snap = memory_state_snapshot(self.store, self.sink, self.scope)
        self.assertEqual(snap, {"memories": [], "deleted": [], "edges": [], "tombstones": []})


if __name__ == "__main__":
    unittest.main()
