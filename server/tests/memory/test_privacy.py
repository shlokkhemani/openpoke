"""Step 2 gate: detectors, ingress scrub, P0, P1."""

from __future__ import annotations

import inspect
import unittest

from server.services.memory import privacy
from server.services.memory.detectors import counts, detect_all
from server.services.memory.models import Candidate

SECRET = "sk-test-SYNTHETIC-12345"
EMAIL = "test.user@example.com"
PROOF2_EMAIL = f"My email is {EMAIL}."
PROOF2_KEY = f"My test API key is {SECRET}."
PROOF2_MIXED = f"My email is {EMAIL}, my test API key is {SECRET}, and I prefer concise emails."

# (sentence as the lab used it, marker, expected class, expected kind)
LAB_MARKERS = [
    (PROOF2_KEY, SECRET, "SECRET", "API_KEY"),
    ("My test API key is sk-test-SYNTHETIC-1234567890abcdef, my fake SSN is 000-12-3456, card 4111 1111 1111 1111.",
     "sk-test-SYNTHETIC-1234567890abcdef", "SECRET", "API_KEY"),
    ("The OpenRouter key is sk-or-v1-SYNTHETIC-LAB-KEY-0000.", "sk-or-v1-SYNTHETIC-LAB-KEY-0000", "SECRET", "API_KEY"),
    ("my fake SSN is 000-12-3456, card", "000-12-3456", "REGULATED_ID", "GOV_ID"),
    ("card 4111 1111 1111 1111.", "4111 1111 1111 1111", "REGULATED_ID", "CARD"),
    ("Your verification code is 482913. Card on file", "482913", "SECRET", "OTP"),
    ("Use code 771204 to sign in.", "771204", "SECRET", "OTP"),
    ("remind me daily that my gate PIN is GATE-PIN-5521", "GATE-PIN-5521", "SECRET", "CREDENTIAL"),
    ("My locker code is LOCKER-7781-SYNTH and my backup email is jane.synthetic@example.test.",
     "LOCKER-7781-SYNTH", "SECRET", "CREDENTIAL"),
    ("my backup email is jane.synthetic@example.test.", "jane.synthetic@example.test", "CONTACT", "EMAIL"),
    (PROOF2_EMAIL, EMAIL, "CONTACT", "EMAIL"),
    ("ships to 42 Synthetic Lane, Springfield.", "42 Synthetic Lane", "PRECISE_LOCATION", "ADDRESS"),
]

FALSE_POSITIVES = ["the code is in main.py", "order 482913 shipped", "meet at 10:30", "$1,234.56", "2026-10-07",
                   "I prefer meetings after 10 AM.", "Actually, my favorite programming language is Rust."]


def cand(**kw) -> Candidate:
    base = dict(candidate_id="cand_1", memory_type="preference", subject="user", predicate="pref.email_style",
                object_entity=None, value="concise", text="User prefers concise emails.", durability="long_term",
                certainty="explicit", evidence="I prefer concise emails")
    base.update(kw)
    return Candidate(**base)


class TestDetectors(unittest.TestCase):
    def test_lab_markers_detected_with_class(self):
        for sentence, marker, cls, kind in LAB_MARKERS:
            with self.subTest(marker=kind + ":" + cls):
                hits = [f for f in detect_all(sentence) if sentence[f.start:f.end] == marker]
                self.assertEqual(len(hits), 1, f"{kind} not detected exactly")
                self.assertEqual((hits[0].cls, hits[0].kind), (cls, kind))

    def test_false_positive_set_untouched(self):
        for text in FALSE_POSITIVES:
            with self.subTest(text=text):
                self.assertEqual(detect_all(text), [])
                self.assertEqual(privacy.ingress_scrub(text), (text, []))
                self.assertEqual(privacy.scrub(text)[0].llm_safe, text)

    def test_trailing_punctuation_preserved(self):
        self.assertEqual(privacy.ingress_scrub("My password is hunter2!")[0], "My password is [SECRET:CREDENTIAL]!")
        self.assertEqual(privacy.ingress_scrub("My gate PIN is GATE-PIN-5521.")[0], "My gate PIN is [SECRET:CREDENTIAL].")
        self.assertEqual(privacy.ingress_scrub(PROOF2_KEY)[0], "My test API key is [SECRET:API_KEY].")

    def test_counts_are_log_safe(self):
        summary = counts(detect_all(PROOF2_MIXED))
        self.assertEqual(summary, [{"type": "API_KEY", "count": 1}, {"type": "EMAIL", "count": 1}])
        self.assertNotIn(SECRET, repr(summary))


class TestIngress(unittest.TestCase):
    def test_ingress_leaves_contacts_replaces_secrets_and_ids(self):
        out, findings = privacy.ingress_scrub(PROOF2_MIXED)
        self.assertEqual(out, f"My email is {EMAIL}, my test API key is [SECRET:API_KEY], and I prefer concise emails.")
        self.assertEqual([(f.cls, f.kind) for f in findings], [("SECRET", "API_KEY")])
        out, _ = privacy.ingress_scrub("my fake SSN is 000-12-3456, card 4111 1111 1111 1111.")
        self.assertEqual(out, "my fake SSN is [GOV_ID], card [CARD].")

    def test_ingress_idempotent(self):
        for sentence, *_ in LAB_MARKERS + [(PROOF2_MIXED,)]:
            once, _ = privacy.ingress_scrub(sentence)
            self.assertEqual(privacy.ingress_scrub(once), (once, []))

    def test_ingress_has_no_reverse_map(self):
        result = privacy.ingress_scrub(PROOF2_MIXED)
        self.assertEqual(len(result), 2)  # (text, findings): nothing else is returned
        for f in result[1]:
            self.assertNotIn(SECRET, repr(f))
        self.assertNotIn("raw_map", inspect.getsource(privacy.ingress_scrub).split('"""')[-1])

    def test_secret_never_persisted_or_sent(self):
        """Ingress + P0 + P1 on the proof-2 strings, then the real MemoryService in-process. Sinks: persisted text,
        LLM_SAFE text, findings, P1 verdicts, extractor input, LTM blocks + notices, ltm.db/-wal/-shm bytes, every
        column of memory_events / memories / memories_fts* tables."""
        sinks = []
        for raw in (PROOF2_EMAIL, PROOF2_KEY, PROOF2_MIXED):
            persisted, ingress_findings = privacy.ingress_scrub(raw)
            sinks.append(persisted)
            sinks.append(repr(ingress_findings))
            scrubbed, raw_map = privacy.scrub(persisted)
            sinks.append(scrubbed.llm_safe)
            sinks.append(repr(scrubbed.findings))
            self.assertNotIn(SECRET, " ".join(raw_map.values()))
        self.assertEqual(sinks[-2], "My email is [EMAIL_1], my test API key is [SECRET:API_KEY], and I prefer concise emails.")

        email_c = cand(candidate_id="c1", memory_type="profile", predicate="profile.email", value="[EMAIL_1]",
                       text="User's email is [EMAIL_1].", evidence="My email is [EMAIL_1]")
        key_c = cand(candidate_id="c2", memory_type="profile", predicate="profile.api_key", value="[SECRET:API_KEY]",
                     text="User's API key is [SECRET:API_KEY].", evidence="my test API key is [SECRET:API_KEY]")
        pref_c = cand(candidate_id="c3")
        v1, v2, v3 = privacy.classify(email_c), privacy.classify(key_c), privacy.classify(pref_c)
        self.assertEqual((v1.action, v1.reasons), ("REJECT", ["CONTACT_IDENTIFIER_NOT_NEEDED"]))
        self.assertIn("CONTACT:EMAIL", v1.detector_types)
        self.assertEqual((v2.action, v2.reasons), ("REJECT", ["SECRET_API_KEY"]))
        self.assertEqual((v3.sensitivity, v3.action), ("LOW", "STORE"))
        sinks += [repr(v) for v in (v1, v2, v3)]
        blob = "\n".join(sinks)
        self.assertNotIn(SECRET, blob)
        self.assertNotIn("SYNTHETIC-12345", blob)

        # In-process service: the same three turns + the draft probe, through prepare_turn / ingest / commit.
        import asyncio
        import shutil
        import tempfile
        from pathlib import Path

        from server.services.memory.models import MemoryScope
        from server.services.memory.store import MemoryStore

        from ._util import all_sql_text, ltm_bytes, make_service, user_turn

        tmp = Path(tempfile.mkdtemp(prefix="ltm-priv-"))
        try:
            store = MemoryStore(tmp / "ltm.db", hmac_key=b"k" * 32)
            scope = MemoryScope("local-user")
            svc = make_service(store, scope)

            async def run():
                out = []
                for raw in (PROOF2_EMAIL, PROOF2_KEY, PROOF2_MIXED, "Draft a short note to Sam about the launch."):
                    out.append(user_turn(svc, raw))
                    self.assertTrue(await svc.await_idle())
                return out

            prepared = asyncio.run(run())
            service_sinks = [ltm_bytes(store).decode("latin-1"), all_sql_text(store),
                             repr(svc.extractor.calls)] + [p.ltm_block + "".join(p.notices) for p in prepared]
            for name, sink in zip(("ltm.db*", "sql", "extractor", "block1", "block2", "block3", "probe"), service_sinks):
                self.assertNotIn(SECRET, sink, name)
                self.assertNotIn("SYNTHETIC-12345", sink, name)
            self.assertNotIn(EMAIL, service_sinks[0])  # contact PII never reaches LTM either
            self.assertNotIn(EMAIL, service_sinks[1])
            self.assertNotIn(EMAIL, service_sinks[2])  # extractor saw [EMAIL_1]
            self.assertIn("[EMAIL_1]", service_sinks[2])
            self.assertIn("User prefers concise emails.", prepared[-1].ltm_block)
            self.assertIn("[SECRET:API_KEY]", prepared[1].notices[0])
            active = [r["canonical_text"] for r in store.all_rows(scope) if r["status"] == "active"]
            self.assertEqual(active, ["User prefers concise emails."])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestP0(unittest.TestCase):
    def test_p0_placeholders_and_map(self):
        scrubbed, raw_map = privacy.scrub("Email jane.synthetic@example.test or test.user@example.com, key sk-test-SYNTHETIC-12345")
        self.assertEqual(scrubbed.llm_safe, "Email [EMAIL_1] or [EMAIL_2], key [SECRET:API_KEY]")
        self.assertEqual(set(raw_map), {"[EMAIL_1]", "[EMAIL_2]"})  # SECRET never mapped

    def test_p0_escapes_user_brackets_but_keeps_ingress_placeholders(self):
        scrubbed, _ = privacy.scrub("see [EMAIL_1] and [note] and [SECRET:API_KEY]")
        self.assertEqual(scrubbed.llm_safe, "see ［EMAIL_1] and ［note] and [SECRET:API_KEY]")


class TestP1(unittest.TestCase):
    def test_literal_secret_in_candidate_rejected(self):
        v = privacy.classify(cand(value=SECRET, text=f"User's key is {SECRET}."))
        self.assertEqual((v.sensitivity, v.action, v.reasons), ("PROHIBITED", "REJECT", ["SECRET_API_KEY"]))

    def test_regulated_rejected(self):
        v = privacy.classify(cand(value="[CARD]", text="User's card is [CARD]."))
        self.assertEqual(v.reasons, ["REGULATED_ID"])

    def test_contact_in_text_only_is_redacted(self):
        c = cand(text="User ([EMAIL_1]) prefers concise emails.")
        v = privacy.classify(c, rerender=lambda c: "User prefers concise emails.")
        self.assertEqual((v.action, v.reasons), ("STORE", ["REDACTED_IDENTIFIER"]))
        self.assertEqual(c.text, "User prefers concise emails.")

    def test_special_category_needs_explicit_remember(self):
        v = privacy.classify(cand(predicate="pref.custom:health", value="adhd medication", text="User takes ADHD medication."))
        self.assertEqual(v.action, "REJECT")
        self.assertEqual(v.reasons[0], "SPECIAL_CATEGORY_NO_CONSENT")
        v = privacy.classify(cand(predicate="pref.custom:health", value="adhd medication",
                                  text="User takes ADHD medication.", explicit_remember=True))
        self.assertEqual((v.sensitivity, v.action), ("HIGH", "STORE"))

    def test_model_category_only_raises(self):
        self.assertEqual(privacy.classify(cand(sensitivity_category="finance")).sensitivity, "MEDIUM")
        self.assertEqual(privacy.classify(cand(predicate="profile.home_city", value="Toronto")).sensitivity, "MEDIUM")


class TestP2(unittest.TestCase):
    def test_egress_flags_values_not_placeholders(self):
        self.assertEqual(privacy.egress_findings("User prefers concise emails. [SECRET:API_KEY]"), [])
        self.assertTrue(privacy.egress_findings(f"User's key is {SECRET}"))


if __name__ == "__main__":
    unittest.main()


class TestBlockerB1(unittest.TestCase):
    """LTM_BLOCKERS.md B1: system ids are not secrets; real high-entropy tokens still are."""

    def test_system_ids_not_flagged_but_random_tokens_are(self):
        from server.services.memory.models import new_id

        for prefix in ("mem", "trc", "run"):
            self.assertEqual(detect_all(new_id(prefix)), [])
        from server.services.memory.events import _event_id

        for _ in range(50):
            self.assertEqual(detect_all(_event_id()), [])
        hits = detect_all("token here: Zx9qL2mN8vB4tR7wK1pS6dF3")
        self.assertEqual([h.kind for h in hits], ["HIGH_ENTROPY"])
        self.assertTrue(detect_all("mem_" + "Zx9qL2mN8vB4tR7wK1pS6dF3"))  # lowercase: not the id grammar


class TestBlockerB2(unittest.TestCase):
    """LTM_BLOCKERS.md B2: typed labels are not credentials; real values next to them still are."""

    def test_labels_not_flagged_values_still_are(self):
        from server.services.memory.privacy import prohibited_findings

        self.assertEqual(prohibited_findings('{"canaries": ["SECRET:API_KEY", "CONTACT:EMAIL"]}'), [])
        self.assertEqual(prohibited_findings('"detectors": ["SECRET:OTP", "SECRET:CREDENTIAL"]'), [])
        self.assertTrue(prohibited_findings("secret: hunter2"))
        self.assertTrue(prohibited_findings(f"SECRET:API_KEY {SECRET}"))

    def test_classify_event_keeps_detector_label(self):
        import asyncio
        import shutil
        import tempfile
        from pathlib import Path

        from server.services.memory.models import MemoryScope
        from server.services.memory.store import MemoryStore

        from ._util import make_service, user_turn

        tmp = Path(tempfile.mkdtemp(prefix="ltm-b2-"))
        try:
            store, scope = MemoryStore(tmp / "ltm.db", hmac_key=b"k" * 32), MemoryScope("u")
            svc = make_service(store, scope)

            async def run():
                p = user_turn(svc, PROOF2_KEY)
                await svc.await_idle()
                return p

            p = asyncio.run(run())
            (ev,) = [e for e in svc.sink.events(scope, p.turn.trace_id) if e["stage"] == "privacy.classify"]
            self.assertEqual((ev["decision"], ev["reason_codes"]), ("REJECT", ["SECRET_API_KEY"]))
            self.assertIn("SECRET:API_KEY", ev["detail"]["detectors"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestReviewM3ProtectedSpanBypass(unittest.TestCase):
    """Review M3: a placeholder/label-shaped prefix must not shield a real credential that follows it."""

    CASES = [("my password is [X]hunter2pass", "hunter2pass"),
             ("SECRET:API_KEY=hunter2pass99", "hunter2pass99"),
             ("Use passphrase: [SECRET:X]realsecret123", "realsecret123")]

    def test_ingress_scrubs_secret_after_protected_prefix(self):
        for raw, secret in self.CASES:
            out, findings = privacy.ingress_scrub(raw)
            self.assertNotIn(secret, out, raw)
            self.assertIn("[SECRET:", out)
            self.assertTrue(findings)
            self.assertEqual(privacy.ingress_scrub(out), (out, []))  # still idempotent
            self.assertNotIn(secret, privacy.scrub(out)[0].llm_safe)

    def test_exact_placeholders_and_labels_still_protected(self):
        for text in ("My test API key is [SECRET:API_KEY].", '"canaries": ["SECRET:API_KEY"]',
                     "card [CARD] and [GOV_ID]", '"detectors": ["SECRET:OTP"]'):
            self.assertEqual(privacy.ingress_scrub(text), (text, []), text)
