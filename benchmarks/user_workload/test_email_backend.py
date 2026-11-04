"""Tests for the isolated benchmark Gmail replacement."""

import json
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "email_messages.json"
BACKEND_PATH = Path(__file__).parents[2] / "server" / "services" / "gmail" / "benchmark_backend.py"
BACKEND_SPEC = importlib.util.spec_from_file_location("benchmark_email_backend", BACKEND_PATH)
assert BACKEND_SPEC and BACKEND_SPEC.loader
BACKEND_MODULE = importlib.util.module_from_spec(BACKEND_SPEC)
BACKEND_SPEC.loader.exec_module(BACKEND_MODULE)
BenchmarkEmailBackend = BACKEND_MODULE.BenchmarkEmailBackend


class BenchmarkEmailFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.day = 0
        self.backend = BenchmarkEmailBackend(
            FIXTURE_PATH,
            now_provider=lambda: datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
            + timedelta(days=self.day),
        )

    def test_fixture_has_unique_message_ids(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        ids = [message["id"] for message in payload["messages"]]
        self.assertEqual(len(ids), 20)
        self.assertEqual(len(ids), len(set(ids)))

    def test_search_finds_relevant_email(self) -> None:
        result = self.backend.execute(
            "GMAIL_FETCH_EMAILS",
            {"query": "Sakura Hotel Tokyo", "max_results": 10},
        )
        messages = result["data"]["messages"]
        self.assertTrue(messages)
        self.assertEqual(messages[0]["threadId"], "sakura-enquiry")

    def test_each_fixture_alias_finds_its_thread(self) -> None:
        self.day = 365
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        for fixture_message in payload["messages"]:
            if not fixture_message["aliases"]:
                continue
            result = self.backend.execute(
                "GMAIL_FETCH_EMAILS",
                {"query": fixture_message["aliases"][0], "max_results": 10},
            )
            threads = {
                message["threadId"] for message in result["data"]["messages"]
            }
            self.assertIn(fixture_message["thread"], threads)

    def test_future_update_is_hidden_until_simulated_day(self) -> None:
        self.day = -40
        early = self.backend.execute(
            "GMAIL_FETCH_EMAILS",
            {"query": "Sakura Hotel Tokyo", "max_results": 10},
        )
        early_ids = {message["messageId"] for message in early["data"]["messages"]}
        self.assertNotIn("user-mail-001", early_ids)

        self.day = 0
        later = self.backend.execute(
            "GMAIL_FETCH_EMAILS",
            {"query": "Sakura Hotel Tokyo", "max_results": 10},
        )
        later_ids = {message["messageId"] for message in later["data"]["messages"]}
        self.assertIn("user-mail-001", later_ids)

    def test_drafts_remain_local(self) -> None:
        created = self.backend.execute(
            "GMAIL_CREATE_EMAIL_DRAFT",
            {"recipient_email": "person@example.test", "subject": "Hello", "body": "Hi"},
        )
        self.assertTrue(created["successful"])
        drafts = self.backend.execute("GMAIL_LIST_DRAFTS", {})
        self.assertEqual(len(drafts["data"]["drafts"]), 1)


if __name__ == "__main__":
    unittest.main()
