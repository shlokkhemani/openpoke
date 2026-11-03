"""Scoped token accounting with fake providers; no network calls."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from server.benchmark_events import record_input_tokens, read_events
from server.openrouter_client import client
from server.services.execution.roster_matcher import RosterMatcher
from .report import input_token_report


class InputTokenTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_keeps_unknown_attempt_instead_of_claiming_complete_usage(self):
        attempts = []
        def handler(request):
            attempts.append(1)
            if len(attempts) == 1:
                raise httpx.ReadTimeout("uncertain delivery", request=request)
            return httpx.Response(200, json={"usage": {"prompt_tokens": 20, "completion_tokens": 7}})
        factory = httpx.AsyncClient
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory}), \
             patch.object(client, "get_settings", return_value=SimpleNamespace(benchmark_mode=True, openrouter_api_key="fake")), \
             patch.object(client.httpx, "AsyncClient", side_effect=lambda: factory(transport=httpx.MockTransport(handler))), \
             patch.object(client.asyncio, "sleep", new_callable=AsyncMock):
            await client.request_chat_completion(model="same-model", messages=[], track_interaction_input=True)
            self.assertEqual([row["input_tokens"] for row in read_events()], [None, 20])
            self.assertEqual([row["request_outcome"] for row in read_events()], ["transport_error", "success"])
            self.assertEqual(read_events()[0]["error_type"], "ReadTimeout")
            self.assertIsNone(read_events()[0]["http_status"])

    async def test_embedding_usage_is_recorded_at_matcher_boundary(self):
        matcher = object.__new__(RosterMatcher)
        matcher._model = "embedding-model"
        matcher._embedding_request = AsyncMock(return_value={
            "data": [{"index": 0, "embedding": [0.5, 1]}], "usage": {"prompt_tokens": 12, "total_tokens": 12}})
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory}):
            await matcher._embed_texts(["private profile"])
            self.assertEqual(len(read_events()), 1)
            self.assertEqual(read_events()[0]["kind"], "embedding")
            self.assertEqual(read_events()[0]["input_tokens"], 12)
            self.assertNotIn("private profile", json.dumps(read_events()))

    async def test_successful_response_with_missing_usage_preserves_identity(self):
        factory = httpx.AsyncClient
        def handler(request):
            return httpx.Response(200, json={"id": "gen-123", "choices": [],
                                            "usage": {"prompt_tokens": None, "completion_tokens": 77}})
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory}), \
             patch.object(client, "get_settings", return_value=SimpleNamespace(benchmark_mode=True, openrouter_api_key="fake")), \
             patch.object(client.httpx, "AsyncClient", side_effect=lambda: factory(transport=httpx.MockTransport(handler))):
            await client.request_chat_completion(model="chat", messages=[], track_interaction_input=True)
            row = read_events()[0]
            self.assertEqual(row["response_id"], "gen-123")
            self.assertEqual(row["request_outcome"], "success")
            self.assertEqual(row["http_status"], 200)
            self.assertEqual(row["input_usage"], {"prompt_tokens": None})
            self.assertIsNone(row["input_tokens"])

    async def test_http_error_is_distinct_from_missing_usage_in_successful_response(self):
        factory = httpx.AsyncClient
        def handler(request):
            return httpx.Response(429, json={"error": {"message": "Rate limited"}, "id": "gen-rate-limit"})
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory}), \
             patch.object(client, "get_settings", return_value=SimpleNamespace(benchmark_mode=True, openrouter_api_key="fake")), \
             patch.object(client.httpx, "AsyncClient", side_effect=lambda: factory(transport=httpx.MockTransport(handler))):
            with self.assertRaises(client.OpenRouterError):
                await client.request_chat_completion(model="chat", messages=[], track_interaction_input=True)
            row = read_events()[0]
            self.assertEqual(row["request_outcome"], "http_error")
            self.assertEqual(row["http_status"], 429)
            self.assertEqual(row["response_id"], "gen-rate-limit")
            self.assertNotIn("Rate limited", json.dumps(row))

    async def test_missing_invalid_and_embedding_total_usage(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory}):
            for usage in ({}, {"prompt_tokens": True}, {"prompt_tokens": -1}, {"total_tokens": 99},
                          {"input_tokens": 0}):
                record_input_tokens("interaction", "chat", {"usage": usage})
            record_input_tokens("embedding", "embed", {"usage": {"total_tokens": 15}})
            self.assertEqual([row["input_tokens"] for row in read_events()], [None, None, None, None, 0, 15])


class InputTokenReportTests(unittest.TestCase):
    def prepare(self, directory, mode, missing=False):
        root = Path(directory)
        events = [dict(event="input_tokens", kind="interaction", input_tokens=100),
                  dict(event="input_tokens", kind="embedding", input_tokens=None if missing else 15)]
        initial = dict(token_tracking_version=1, metrics_events=[], routing={"mode": mode})
        (root / "application_events.json").write_text(json.dumps(events))
        (root / "final_snapshot.json").write_text(json.dumps(dict(token_tracking_version=1, metrics_events=events)))
        return root, initial

    def test_mode_totals_include_only_requested_scope(self):
        for mode, total in (("full_roster", 100), ("shortlist", 115)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root, initial = self.prepare(directory, mode)
                result = input_token_report(root, initial, True)
                self.assertTrue(result["complete"])
                self.assertEqual(result["total_input_tokens"], total)
                self.assertEqual(result["interaction"]["input_tokens"], 100)
                self.assertEqual(result["embedding"]["input_tokens"], 15)

    def test_missing_usage_or_partial_run_does_not_claim_exact_total(self):
        with tempfile.TemporaryDirectory() as directory:
            root, initial = self.prepare(directory, "shortlist", missing=True)
            result = input_token_report(root, initial, True)
            self.assertFalse(result["complete"])
            self.assertIsNone(result["total_input_tokens"])
            self.assertEqual(result["embedding"]["missing_usage_calls"], 1)
            self.assertEqual(result["interaction"]["known_input_tokens"], 100)
            root, initial = self.prepare(directory, "shortlist")
            self.assertIsNone(input_token_report(root, initial, False)["total_input_tokens"])
            (root / "application_events.json").write_text("[]")
            self.assertFalse(input_token_report(root, initial, True)["complete"])

    def test_historical_runs_are_unavailable_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            result = input_token_report(Path(directory), {}, True)
            self.assertFalse(result["available"])
            self.assertIsNone(result["total_input_tokens"])
            self.assertIsNone(result["interaction"]["input_tokens"])


if __name__ == "__main__":
    unittest.main()
