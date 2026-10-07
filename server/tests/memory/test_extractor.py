"""Step 4 gate: C4 grammar, C5 clause split, clause reporting, grounding."""

from __future__ import annotations

import unittest

from server.services.memory import vocab
from server.services.memory.extractor import RuleExtractor, grounded, report_clauses, split_clauses, validate
from server.services.memory.models import Candidate
from server.services.memory.privacy import ingress_scrub, scrub

MIXED_LLM_SAFE = "My email is [EMAIL_1], my test API key is [SECRET:API_KEY], and I prefer concise emails."
SELECTIVE = "I prefer meetings after 10 AM. I'm eating a turkey sandwich right now."


def extract(text):
    return RuleExtractor().extract_sync(text)


def only(result):
    assert len(result.candidates) == 1, result
    return result.candidates[0]


class TestGrammar(unittest.TestCase):
    def test_favorite_language_and_correction(self):
        c = only(extract("My favorite programming language is Python."))
        self.assertEqual((c.predicate, c.value, c.is_correction, c.certainty), (
            "pref.favorite_programming_language", "Python", False, "explicit"))
        self.assertEqual(c.text, "User's favorite programming language is Python.")
        c = only(extract("Actually, my favorite programming language is Rust."))
        self.assertEqual((c.predicate, c.value, c.is_correction), ("pref.favorite_programming_language", "Rust", True))
        self.assertEqual(vocab.canonical_value(c.predicate, c.value), "rust")

    def test_meeting_time(self):
        for text, window in (("I prefer meetings after 10 AM.", {"after": "10:00"}),
                             ("I prefer meetings before 5 PM.", {"before": "17:00"}),
                             ("I prefer meetings between 10 AM and 2 PM.", {"between": ["10:00", "14:00"]}),
                             ("Actually I prefer meetings after 1 PM now.", {"after": "13:00"})):
            with self.subTest(text=text):
                c = only(extract(text))
                self.assertEqual(c.predicate, "pref.meeting_time")
                self.assertEqual(vocab.parse_time_window(c.value), window)
        self.assertEqual(only(extract("I prefer meetings after 10 AM.")).text, "User prefers meetings after 10 AM.")

    def test_email_style_aliases(self):
        for word in ("concise", "short", "brief"):
            c = only(extract(f"I prefer {word} emails."))
            self.assertEqual((c.predicate, vocab.canonical_value(c.predicate, c.value)), ("pref.email_style", "concise"))
            self.assertEqual(c.text, "User prefers concise emails.")
        c = only(extract("I prefer detailed emails."))
        self.assertEqual(vocab.canonical_value(c.predicate, c.value), "detailed")

    def test_email_and_api_key_are_extractor_only_predicates(self):
        res = extract(MIXED_LLM_SAFE)
        self.assertEqual([c.predicate for c in res.candidates], ["profile.email", "profile.api_key", "pref.email_style"])
        self.assertEqual(res.candidates[0].value, "[EMAIL_1]")
        self.assertEqual(res.candidates[1].value, "[SECRET:API_KEY]")
        self.assertFalse(vocab.is_storable("profile.email"))
        self.assertFalse(vocab.is_storable("profile.api_key"))
        self.assertEqual(only(extract("My test API key is [SECRET:API_KEY].")).predicate, "profile.api_key")
        self.assertEqual(only(extract("My email is [EMAIL_1].")).predicate, "profile.email")

    def test_questions_are_no_candidate(self):
        for q in ("What's my favorite programming language?", "When should I schedule a meeting?", "What's 2+2?"):
            res = extract(q)
            self.assertEqual(res.candidates, [])
            self.assertEqual([i.reason for i in res.ignored], ["QUESTION"])

    def test_small_grammar_extras(self):
        self.assertEqual(only(extract("My manager is Alice.")).predicate, "rel.manager")
        c = only(extract("Never email Bob without asking me."))
        self.assertEqual((c.predicate, c.object_entity), ("constraint.confirm_before_email", "person:bob"))
        c = only(extract("I'm working on OpenPoke memory this week."))
        self.assertEqual((c.predicate, c.durability), ("project.current", "short_term"))


class TestClauses(unittest.TestCase):
    def test_proof2_mixed_message_is_exactly_three_clauses(self):
        clauses = split_clauses(MIXED_LLM_SAFE)
        self.assertEqual(clauses, ["My email is [EMAIL_1]", "my test API key is [SECRET:API_KEY]",
                                   "I prefer concise emails."])
        # The pipeline order produces that input: ingress, then P0.
        raw = "My email is test.user@example.com, my test API key is sk-test-SYNTHETIC-12345, and I prefer concise emails."
        self.assertEqual(scrub(ingress_scrub(raw)[0])[0].llm_safe, MIXED_LLM_SAFE)

    def test_comma_split_needs_verbs_on_both_sides(self):
        self.assertEqual(split_clauses("Actually, my favorite programming language is Rust."),
                         ["Actually, my favorite programming language is Rust."])
        self.assertEqual(split_clauses("Paris, London and Rome are nice."), ["Paris, London and Rome are nice."])

    def test_every_clause_reported(self):
        res = extract(MIXED_LLM_SAFE)
        rep = report_clauses(MIXED_LLM_SAFE, res.candidates, res.ignored)
        self.assertEqual([r["candidate_id"] for r in rep], ["cand_1", "cand_2", "cand_3"])


class TestSelective(unittest.TestCase):
    def test_turkey_sandwich_ignored_preference_stored(self):
        """Extraction level, then the real MemoryService: preference STORE -> ACTIVE, sandwich IGNORE, no sandwich row."""
        res = extract(SELECTIVE)
        self.assertEqual(len(res.candidates), 1)
        self.assertEqual(res.candidates[0].predicate, "pref.meeting_time")
        rep = report_clauses(SELECTIVE, res.candidates, res.ignored)
        self.assertEqual([(r["clause"], r["candidate_id"], r["reason"]) for r in rep], [
            ("I prefer meetings after 10 AM.", "cand_1", None),
            ("I'm eating a turkey sandwich right now.", None, "TRANSIENT_STATE"),
        ])

        import asyncio
        import shutil
        import tempfile
        from pathlib import Path

        from server.services.memory.models import MemoryScope
        from server.services.memory.store import MemoryStore
        from server.services.memory.trace import assemble_turn_trace

        from ._util import make_service, user_turn

        tmp = Path(tempfile.mkdtemp(prefix="ltm-sel-"))
        try:
            store = MemoryStore(tmp / "ltm.db", hmac_key=b"k" * 32)
            scope = MemoryScope("local-user")
            svc = make_service(store, scope)

            async def run():
                p = user_turn(svc, SELECTIVE)
                await svc.await_idle()
                return p

            p = asyncio.run(run())
            rows = store.all_rows(scope)
            self.assertEqual([(r["canonical_text"], r["status"], r["importance"]) for r in rows],
                             [("User prefers meetings after 10 AM.", "active", 0.8)])
            t = assemble_turn_trace(svc.sink, scope, p.turn.trace_id)
            self.assertEqual([(o["decision"], o["result"]) for o in t["outcomes"]],
                             [("STORE", "INSERT"), ("IGNORE", "NO_CANDIDATE")])
            self.assertEqual(t["outcomes"][1]["reason"], "TRANSIENT_STATE")
            self.assertEqual(t["outcomes"][1]["label"], "eating a turkey sandwich right now")
            self.assertTrue(all("sandwich" not in (r["canonical_text"] or "") for r in rows))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestGrounding(unittest.TestCase):
    def _cand(self, **kw):
        base = dict(candidate_id="cand_9", memory_type="preference", subject="user",
                    predicate="pref.favorite_programming_language", object_entity=None, value="Haskell",
                    text="User's favorite programming language is Haskell.", durability="long_term",
                    certainty="explicit", evidence="")
        base.update(kw)
        return Candidate(**base)

    def test_ungrounded_value_dropped(self):
        source = "My favorite programming language is Python."
        kept, dropped = validate([self._cand()], source)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0][1], "UNGROUNDED")

    def test_invented_evidence_dropped(self):
        c = self._cand(value="Python", evidence="my favorite language is definitely Python")
        self.assertFalse(grounded(c, "My favorite programming language is Python."))

    def test_time_paraphrase_grounds(self):
        c = self._cand(predicate="pref.meeting_time", value="after 10:00", evidence="I prefer meetings after 10 AM")
        self.assertTrue(grounded(c, "I prefer meetings after 10 AM."))

    def test_alias_remap_and_schema_drop(self):
        c = self._cand(predicate="pref.meeting_hours", value="after 10 AM", evidence="")
        kept, _ = validate([c], "I prefer meetings after 10 AM.")
        self.assertEqual(kept[0].predicate, "pref.meeting_time")
        bad = self._cand(predicate="pref.made_up_thing", value="x")
        self.assertEqual(validate([bad], "x")[1][0][1], "SCHEMA")
        bad_enum = self._cand(durability="forever", value="Python")
        self.assertEqual(validate([bad_enum], "Python")[1][0][1], "SCHEMA")


if __name__ == "__main__":
    unittest.main()
