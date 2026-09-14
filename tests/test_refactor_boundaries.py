"""Deterministic coverage for the refactored context and tool boundaries."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server.agents.execution_agent.context.results import ResultStore, resolve_body_from
from server.agents.execution_agent.tools import get_tool_registry as get_execution_registry
from server.agents.execution_agent.tools import get_tool_schemas as get_execution_schemas
from server.agents.interaction_agent.tools import (
    get_execution_batch_manager,
    get_tool_schemas as get_interaction_schemas,
    set_execution_batch_manager,
)
from server.config import get_settings
from server.context.overflow import RESULT_TOO_LARGE, is_context_overflow, terminal_overflow_message
from server.context.preview import preview_text
import server.agents.interaction_agent.tools.legacy as legacy_tools


def _schema_names(schemas):
    return [schema["function"]["name"] for schema in schemas]


class StrategyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.original_strategy = self.settings.context_strategy
        self.original_digest = self.settings.interaction_digest_enabled
        self.original_roster = self.settings.roster_v2_enabled

    def tearDown(self):
        self.settings.context_strategy = self.original_strategy
        self.settings.interaction_digest_enabled = self.original_digest
        self.settings.roster_v2_enabled = self.original_roster

    def test_legacy_schema_surface_excludes_budgeted_tools(self):
        self.settings.context_strategy = "legacy"

        self.assertEqual(
            _schema_names(get_interaction_schemas()),
            ["send_message_to_agent", "send_message_to_user", "send_draft", "wait"],
        )
        execution_names = _schema_names(get_execution_schemas())
        self.assertNotIn("recall_worker_history", execution_names)
        self.assertNotIn("read_email", execution_names)
        self.assertNotIn("digest_email", execution_names)

    def test_budgeted_schema_surface_is_complete_and_has_runtime_handlers(self):
        self.settings.context_strategy = "budgeted"
        self.settings.interaction_digest_enabled = True
        self.settings.roster_v2_enabled = True

        interaction_names = _schema_names(get_interaction_schemas())
        self.assertIn("recall_history", interaction_names)
        self.assertIn("digest_entry", interaction_names)
        self.assertIn("find_worker", interaction_names)

        execution_names = _schema_names(get_execution_schemas())
        for name in ("recall_worker_history", "gmail_create_draft_v2", "read_email", "digest_email"):
            self.assertIn(name, execution_names)

        registry = get_execution_registry("unit-test-worker")
        self.assertIn("recall_worker_history", registry)
        # These tools need per-run ResultStore state and are intentionally handled by the runtime.
        self.assertNotIn("read_email", registry)
        self.assertNotIn("digest_email", registry)


class BatchManagerInjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_replacement_reaches_the_dispatch_implementation(self):
        original = get_execution_batch_manager()

        class FakeManager:
            def __init__(self):
                self.calls = []

            async def execute_agent(self, agent_name, instructions):
                self.calls.append((agent_name, instructions))
                return SimpleNamespace(success=True)

        replacement = FakeManager()
        roster = Mock()
        roster.get_agents.return_value = []
        logs = Mock()
        try:
            set_execution_batch_manager(replacement)
            self.assertIs(get_execution_batch_manager(), replacement)
            with patch.object(legacy_tools, "get_agent_roster", return_value=roster), patch.object(
                legacy_tools, "get_execution_agent_logs", return_value=logs
            ):
                result = legacy_tools.send_message_to_agent("Test Worker", "Do the deterministic thing")
                await asyncio.sleep(0)

            self.assertTrue(result.success)
            self.assertEqual(replacement.calls, [("Test Worker", "Do the deterministic thing")])
            roster.add_agent.assert_called_once_with("Test Worker")
            logs.record_request.assert_called_once_with("Test Worker", "Do the deterministic thing")
        finally:
            set_execution_batch_manager(original)


class SharedContextTests(unittest.TestCase):
    def test_preview_is_bounded_and_keeps_both_ends(self):
        text = "HEAD" + ("x" * 1000) + "TAIL"
        preview = preview_text(text, 50, note="unit test")

        self.assertLess(len(preview), len(text))
        self.assertTrue(preview.startswith("HEAD"))
        self.assertTrue(preview.endswith("TAIL"))
        self.assertIn("characters omitted: unit test", preview)

    def test_overflow_classification_and_terminal_message(self):
        self.assertTrue(is_context_overflow("maximum context length exceeded"))
        self.assertFalse(is_context_overflow("temporary network failure"))
        self.assertIn(RESULT_TOO_LARGE, terminal_overflow_message("test prompt"))

    def test_result_store_bounds_email_bodies_but_keeps_full_text_for_recall(self):
        store = ResultStore()
        result = [{"id": "message-1", "subject": "Status", "clean_text": "z" * 2000}]
        store.remember("call-1", result)

        bounded = store.bound(result, per_email_tokens=20, total_tokens=1000)
        self.assertLess(len(bounded[0]["clean_text"]), 2000)
        self.assertEqual(store.emails["message-1"]["clean_text"], "z" * 2000)

        body, error = resolve_body_from({"source": "email", "id": "message-1"}, store)
        self.assertIsNone(error)
        self.assertEqual(body, "z" * 2000)


if __name__ == "__main__":
    unittest.main()
