from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import httpx

from server.agents.interaction_agent import runtime as interaction_runtime
from server.config import Settings
from server.openrouter_client import client as model_client

from server.agents.interaction_agent.agent import prepare_message_with_history
from server.services.execution.log_store import ExecutionAgentLogStore
from server.services.execution.roster import AgentRoster
from server.services.execution.roster_matcher import RosterMatcher, _cosine_similarity


class RosterMatcherTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        root = Path(self._temp_dir.name)
        self.roster = AgentRoster(root / "roster.json")
        self.logs = ExecutionAgentLogStore(root / "logs")
        self.index_path = root / "roster_embeddings.json"

        for name in ["Vercel Job Offer", "Dinner Reservation", "Monthly Invoices"]:
            self.roster.add_agent(name)

        self.logs.record_request(
            "Vercel Job Offer",
            "Find the latest email from the Vercel recruiter",
        )
        self.logs.record_request(
            "Dinner Reservation",
            "Find a restaurant and reserve a table for Friday",
        )
        self.logs.record_request(
            "Monthly Invoices",
            "Collect this month's invoices and receipts",
        )

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    async def test_both_runtime_modes_apply_to_user_and_agent_messages(self) -> None:
        for enabled in (False, True):
            with self.subTest(shortlisting=enabled):
                matcher = Mock(shortlist=AsyncMock(return_value=["Vercel Job Offer"]))
                with patch.object(interaction_runtime, "get_settings", return_value=Settings(
                    openrouter_api_key="fake", roster_shortlisting_enabled=enabled)), \
                     patch.object(interaction_runtime, "get_conversation_log"), \
                     patch.object(interaction_runtime, "get_working_memory_log"), \
                     patch.object(interaction_runtime, "get_roster_matcher", return_value=matcher) as get_matcher, \
                     patch("server.agents.interaction_agent.agent.get_agent_roster", return_value=self.roster):
                    runtime = interaction_runtime.InteractionAgentRuntime()
                    runtime._load_conversation_transcript = Mock(return_value="")
                    runtime._run_interaction_loop = AsyncMock(return_value=interaction_runtime._LoopSummary())
                    runtime._finalize_response = Mock(return_value="Done")
                    for handler in (runtime.execute, runtime.handle_agent_message):
                        result = await handler("Reply to the recruiter")
                        self.assertTrue(result.success, result.error)
                        content = runtime._run_interaction_loop.call_args.args[1][0]["content"]
                        self.assertIn('name="Vercel Job Offer"', content)
                        self.assertEqual('name="Dinner Reservation"' in content, not enabled)
                    self.assertEqual(matcher.shortlist.await_count, 2 if enabled else 0)
                    self.assertEqual(get_matcher.call_count, 1 if enabled else 0)

    async def test_embedding_cache_is_isolated_per_run(self) -> None:
        requests = []
        def handler(request):
            payload = json.loads(request.content)
            texts = payload["input"]
            requests.append(texts)
            self.assertEqual(payload["encoding_format"], "float")
            return httpx.Response(200, json={
                "data": [{"index": i, "embedding": [1.0, 0.0]} for i in range(len(texts))],
            })
        factory = httpx.AsyncClient
        for run in ("first", "second"):
            data_dir = Path(self._temp_dir.name) / run
            with patch.dict(os.environ, {"OPENPOKE_DATA_DIR": str(data_dir),
                                         "OPENPOKE_BENCHMARK_MODE": "1"}), \
                 patch.object(model_client, "_headers", return_value={}), \
                 patch.object(model_client.httpx, "AsyncClient", side_effect=lambda: factory(
                     transport=httpx.MockTransport(handler))):
                matcher = RosterMatcher(roster=self.roster, logs=self.logs, model="fake", min_size=1)
                await matcher.shortlist("Find an agent")
                await matcher.shortlist("Find another agent")
                self.assertTrue((data_dir / "execution_agents/roster_embeddings.json").is_file())
        # Each fresh run pays for its own profiles; subsequent queries reuse them.
        self.assertEqual([len(texts) for texts in requests], [1, 3, 1, 1, 3, 1])

    async def test_returns_semantically_closest_agent_and_persists_profiles(
        self,
    ) -> None:
        calls: List[List[str]] = []

        async def fake_embeddings(**kwargs: Any) -> Dict[str, Any]:
            texts = list(kwargs["input"])
            calls.append(texts)
            data = []
            for index, text in enumerate(texts):
                lowered = text.lower()
                if "vercel" in lowered or "recruiter" in lowered:
                    vector = [1.0, 0.0]
                elif "dinner" in lowered or "restaurant" in lowered:
                    vector = [0.0, 1.0]
                else:
                    vector = [0.2, 0.8]
                data.append({"index": index, "embedding": vector})
            return {"data": data}

        matcher = RosterMatcher(
            roster=self.roster,
            logs=self.logs,
            model="test-embedding-model",
            min_size=1,
            recent_task_limit=3,
            index_path=self.index_path,
            embedding_request=fake_embeddings,
        )

        first = await matcher.shortlist("Draft a reply to the Vercel recruiter")
        second = await matcher.shortlist("Follow up with the Vercel recruiter")

        self.assertEqual(first, ["Vercel Job Offer"])
        self.assertEqual(second, ["Vercel Job Offer"])
        self.assertEqual(len(calls), 3)  # Query + profiles, then only the next query.

        persisted = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.assertEqual(set(persisted["entries"]), set(self.roster.get_agents()))

    async def test_propagates_error_when_embedding_provider_fails(self) -> None:
        async def failing_embeddings(**_kwargs: Any) -> Dict[str, Any]:
            raise RuntimeError("provider unavailable")

        matcher = RosterMatcher(
            roster=self.roster,
            logs=self.logs,
            model="test-embedding-model",
            min_size=1,
            index_path=self.index_path,
            embedding_request=failing_embeddings,
        )

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            await matcher.shortlist("Reply to the recruiter")

    async def test_small_roster_does_not_call_embedding_provider(self) -> None:
        called = False

        async def fake_embeddings(**_kwargs: Any) -> Dict[str, Any]:
            nonlocal called
            called = True
            return {"data": []}

        matcher = RosterMatcher(
            roster=self.roster,
            logs=self.logs,
            model="test-embedding-model",
            min_size=3,
            index_path=self.index_path,
            embedding_request=fake_embeddings,
        )

        result = await matcher.shortlist("Anything")

        self.assertEqual(result, self.roster.get_agents())
        self.assertFalse(called)

    async def test_shortlist_size_grows_with_roster_and_respects_limits(self) -> None:
        async def fake_embeddings(**kwargs: Any) -> Dict[str, Any]:
            return {"data": [
                {"index": index, "embedding": [1.0, 0.0]}
                for index, _ in enumerate(kwargs["input"])
            ]}

        matcher = RosterMatcher(
            roster=self.roster,
            logs=self.logs,
            model="test-embedding-model",
            percentage=12.5,
            min_size=2,
            max_size=5,
            index_path=self.index_path,
            embedding_request=fake_embeddings,
        )
        # Same matcher sees roster growth: minimum, exact percentage, rounding,
        # and maximum. Equal scores preserve roster order.
        for roster_size, expected_size in [(3, 2), (16, 2), (17, 3), (48, 5)]:
            with self.subTest(roster_size=roster_size):
                for index in range(len(self.roster.get_agents()), roster_size):
                    self.roster.add_agent(f"Agent {index}")
                result = await matcher.shortlist("Find an agent")
                self.assertEqual(result, self.roster.get_agents()[:expected_size])

    async def test_empty_roster_does_not_call_embedding_provider(self) -> None:
        async def unexpected_embeddings(**_kwargs: Any) -> Dict[str, Any]:
            self.fail("Empty roster should not require embeddings")

        self.roster.clear()
        matcher = RosterMatcher(
            roster=self.roster,
            logs=self.logs,
            model="test-embedding-model",
            index_path=self.index_path,
            embedding_request=unexpected_embeddings,
        )
        self.assertEqual(await matcher.shortlist("Find an agent"), [])

    def test_rejects_invalid_shortlist_settings(self) -> None:
        for options in [
            {"percentage": 0},
            {"percentage": -1},
            {"percentage": 101},
            {"percentage": float("nan")},
            {"percentage": float("inf")},
            {"min_size": 0},
            {"min_size": 6, "max_size": 5},
        ]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                RosterMatcher(
                    roster=self.roster,
                    logs=self.logs,
                    model="test-embedding-model",
                    **options,
                )

    def test_cosine_similarity_rejects_mismatched_dimensions(self) -> None:
        with self.assertRaises(ValueError):
            _cosine_similarity([1.0], [1.0, 2.0])


class InteractionMessageTests(unittest.TestCase):
    def test_only_supplied_shortlist_is_rendered(self) -> None:
        messages = prepare_message_with_history(
            "Reply to the recruiter",
            "",
            active_agents=["Vercel Job Offer", "Recruiter Emails"],
        )

        content = messages[0]["content"]
        self.assertIn('<agent name="Vercel Job Offer" />', content)
        self.assertIn('<agent name="Recruiter Emails" />', content)
        self.assertNotIn("Dinner Reservation", content)


if __name__ == "__main__":
    unittest.main()
