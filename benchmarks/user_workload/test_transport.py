"""Exercise real HTTP-client parsing against mocked transports, never providers."""
import os
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from server.benchmark_events import read_events
from server.openrouter_client import client
from server.routes import benchmark as benchmark_routes
from server.config import Settings
from server.services.gmail import client as gmail_client
from server.services.gmail.benchmark_backend import BenchmarkEmailBackend
from server.agents.interaction_agent.runtime import InteractionAgentRuntime
from .__main__ import ROOT


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_interaction_input_usage_is_tracked(self):
        requests = []
        def handler(request):
            requests.append(request)
            if request.url.path.endswith("embeddings"):
                return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1]}]})
            return httpx.Response(200, json={"id": "response-1", "choices": [],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
        factory = httpx.AsyncClient
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory,
        }), patch.object(client, "get_settings", return_value=SimpleNamespace(
            benchmark_mode=True, openrouter_api_key="never-a-real-key")), \
            patch.object(client.httpx, "AsyncClient", side_effect=lambda: factory(transport=httpx.MockTransport(handler))):
            runtime = object.__new__(InteractionAgentRuntime)
            runtime.model, runtime.api_key, runtime.tool_schemas = "chat", "never-a-real-key", []
            await runtime._make_llm_call("private prompt", [])
            # Other agents can use the same model; model name must not define scope.
            await client.request_chat_completion(model="chat", messages=[])
            await client.request_embeddings(model="embed", input=["private embedding input"])
            events = read_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["kind"], "interaction")
            self.assertEqual(events[0]["input_tokens"], 10)
            self.assertEqual(events[0]["http_status"], 200)
            self.assertEqual(events[0]["request_outcome"], "success")
            self.assertNotIn("completion_tokens", events[0]["input_usage"])
            for request in requests:
                self.assertNotIn("usage", json.loads(request.content))
            self.assertEqual(requests[0].extensions["timeout"]["read"], 180.0)
            self.assertEqual(requests[0].extensions["timeout"]["connect"], 60.0)

    async def test_timeout_change_is_benchmark_only_and_configurable(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"choices": []})
        factory = httpx.AsyncClient
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory,
            "OPENPOKE_BENCHMARK_MODEL_READ_TIMEOUT": "240",
        }), patch.object(client.httpx, "AsyncClient", side_effect=lambda: factory(transport=httpx.MockTransport(handler))):
            for mode, expected in ((False, 60.0), (True, 240.0)):
                with patch.object(client, "get_settings", return_value=SimpleNamespace(
                    benchmark_mode=mode, openrouter_api_key="fake")):
                    await client.request_chat_completion(model="test", messages=[])
                self.assertEqual(requests[-1].extensions["timeout"]["read"], expected)

    async def test_transport_failure_is_not_retried_in_either_mode(self):
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                raise httpx.ReadTimeout("mock timeout", request=request)
            return httpx.Response(200, json={"choices": []})
        factory = httpx.AsyncClient
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory,
        }), patch.object(client.httpx, "AsyncClient", side_effect=lambda: factory(transport=httpx.MockTransport(handler))):
            for mode in (False, True):
                calls.clear()
                with self.subTest(benchmark_mode=mode), patch.object(
                    client, "get_settings", return_value=SimpleNamespace(
                        benchmark_mode=mode, openrouter_api_key="fake")
                ):
                    with self.assertRaises(client.OpenRouterError):
                        await client.request_chat_completion(model="chat", messages=[])
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(read_events(), [])

    async def test_http_error_is_not_retried(self):
        factory = httpx.AsyncClient
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429, json={"error": "mock rate limit"})
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory,
        }), patch.object(client, "get_settings", return_value=SimpleNamespace(
            benchmark_mode=True, openrouter_api_key="fake")), \
            patch.object(client.httpx, "AsyncClient", side_effect=lambda: factory(transport=httpx.MockTransport(handler))):
            with self.assertRaises(client.OpenRouterError):
                await client.request_chat_completion(model="chat", messages=[])
            self.assertEqual(len(calls), 1)
            self.assertEqual(read_events(), [])


class ApiEvidenceTests(unittest.TestCase):
    def test_local_email_gateway_records_full_actions_and_errors(self):
        backend = BenchmarkEmailBackend(ROOT / "email_messages.json")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory,
        }), patch.object(gmail_client, "_get_benchmark_backend", return_value=backend):
            gmail_client.execute_gmail_tool("GMAIL_CREATE_EMAIL_DRAFT", "fake", arguments={
                "recipient_email": "contact@example.test", "subject": "GB-88", "body": "$2,400"})
            with self.assertRaises(ValueError):
                gmail_client.execute_gmail_tool("UNSUPPORTED", "fake")
            actions = read_events()
            self.assertEqual(actions[0]["arguments"]["body"], "$2,400")
            self.assertTrue(actions[0]["succeeded"])
            self.assertFalse(actions[1]["succeeded"])
            self.assertEqual(backend.snapshot()["drafts"][0]["subject"], "GB-88")

    def test_snapshot_exports_outcome_evidence_without_usage(self):
        backend = BenchmarkEmailBackend(ROOT / "email_messages.json")
        logs, conversation, triggers = Mock(), Mock(), Mock()
        conversation.iter_entries.return_value = [("poke_reply", "time", "Actual draft")]
        triggers.list_all_triggers.return_value = []
        settings = Settings(benchmark_mode=True)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory,
        }), patch.object(benchmark_routes, "_status_payload", return_value={"idle": True, "roster_agents": []}), \
            patch.object(benchmark_routes, "get_execution_agent_logs", return_value=logs), \
            patch.object(benchmark_routes, "get_conversation_log", return_value=conversation), \
            patch.object(benchmark_routes, "get_trigger_service", return_value=triggers), \
            patch.object(benchmark_routes, "benchmark_email_fixture_enabled", return_value=True), \
            patch.object(benchmark_routes, "_get_benchmark_backend", return_value=backend):
            result = benchmark_routes.benchmark_snapshot(settings)
            self.assertEqual(result["metrics_version"], 1)
            self.assertEqual(result["routing"]["mode"], "full_roster")
            self.assertEqual(result["conversation"][0]["content"], "Actual draft")
            self.assertEqual(len(result["email_state"]["inbox"]), 20)
            self.assertNotIn("token_usage", result)
            self.assertEqual(benchmark_routes.benchmark_metrics(settings),
                             {"metrics_events": [], "token_tracking_version": 1})
            self.assertEqual(result["token_tracking_version"], 1)
