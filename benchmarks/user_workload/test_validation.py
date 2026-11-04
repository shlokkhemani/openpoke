"""Check the input contract consumed by the external matcher runner."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from .__main__ import FILES, ROOT, load_messages
from .run import Runner
from .schedule import load_groups


class MessageContractTests(unittest.TestCase):
    def test_schedules_cover_every_message_once(self):
        for messages_file, schedule_file, burst_count in (
            ("setup_messages", "setup_schedule", 10),
            ("test_messages", "test_schedule", 3),
        ):
            count = len(load_messages(ROOT / f"{messages_file}.json"))
            groups = load_groups(ROOT / f"{schedule_file}.json", count)
            indices = [i for start, offsets in groups for i in range(start, start + len(offsets))]
            self.assertEqual(indices, list(range(1, count + 1)))
            self.assertEqual(sum(len(offsets) > 1 for _, offsets in groups), burst_count)

    def test_rejects_invalid_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.json"
            for bursts in (
                [{"start_message": 1, "offsets_seconds": [1, 2]}],
                [{"start_message": 1, "offsets_seconds": [0, -1]}],
                [{"start_message": 3, "offsets_seconds": [0, 1]}],
                [{"start_message": 1, "offsets_seconds": [0, float("nan")]}],
                [{"start_message": 1, "offsets_seconds": [0, 1]},
                 {"start_message": 2, "offsets_seconds": [0, 1]}],
            ):
                path.write_text(json.dumps({"bursts": bursts}), encoding="utf-8")
                with self.subTest(bursts=bursts), self.assertRaises(ValueError):
                    load_groups(path, 3)

    def test_bootstrap_inbox_is_visible_at_initial_clock_and_has_unique_ids(self):
        payload = json.loads((ROOT / "email_messages.json").read_text())
        ids = [m["id"] for m in payload["messages"]]
        self.assertEqual(len(ids), len(set(ids)))
        initial_time = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        for message in payload["messages"]:
            for field in ("id", "thread", "timestamp", "subject", "sender", "to", "body"):
                self.assertTrue(message[field])
            self.assertLess(datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00")), initial_time)

    def test_workloads_contain_only_unique_user_strings(self):
        messages = [message for name in FILES
                    for message in load_messages(ROOT / f"{name}.json")]
        self.assertEqual(len(messages), len(set(messages)))
        self.assertEqual(len(load_messages(ROOT / "test_messages.json")), 20)
        self.assertEqual(len(load_messages(ROOT / "setup_messages.json")), 150)

    def test_rejects_generated_agent_records_and_invalid_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "messages.json"
            for payload in ({"roster": []}, [{"agent_name": "invented"}],
                            [], [" "], ["hello", "hello"]):
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_messages(path)


class RunnerTests(unittest.TestCase):
    def test_burst_submits_while_busy_then_waits_for_all_messages(self):
        runner = Runner("http://test", poll=0, idle_grace=0)
        sent, records, now = [], [], [0.0]
        def request(method, path, payload=None):
            if method == "POST":
                sent.append(payload["messages"][0]["content"])
                return 202, {}
            state = self.state(len(sent), idle=len(sent) in (0, 3))
            state["active_interactions"] = int(len(sent) in (1, 2))
            return 200, state
        def sleep(delay):
            now[0] += delay
        runner.request = request
        with patch("benchmarks.user_workload.run.time.monotonic", side_effect=lambda: now[0]), \
             patch("benchmarks.user_workload.run.time.sleep", side_effect=sleep):
            result = runner.send_group(["first", "correction", "unrelated"], [0, 2, 4], 1, records.append)
        self.assertEqual(sent, ["first", "correction", "unrelated"])
        submissions = [r for r in records if r["event"] == "submitting"]
        self.assertEqual([r["actual_offset_seconds"] for r in submissions], [0, 2, 4])
        self.assertEqual(result["observed_overlapping_messages"], 2)
        self.assertEqual(result["last_index"], 3)

    def test_fast_previous_response_is_not_falsely_reported_as_overlap(self):
        runner = Runner("http://test", poll=0, idle_grace=0)
        sent = []
        def request(method, path, payload=None):
            if method == "POST":
                sent.append(payload)
                return 202, {}
            return 200, self.state(len(sent))
        runner.request = request
        result = runner.send_group(["first", "second"], [0, 0], 1, lambda r: None)
        self.assertEqual(result["observed_overlapping_messages"], 0)

    def test_wait_rejects_unexpected_extra_user_messages(self):
        runner = Runner("http://test", poll=0)
        runner.request = lambda *args: (200, self.state(4))
        with self.assertRaisesRegex(RuntimeError, "Concurrent user"):
            runner.wait(self.state(), message_count=3)

    def state(self, count=0, idle=True, failures=0):
        return dict(benchmark_mode=True, isolated_data_dir=True, isolated_tools=True,
                    idle=idle, user_message_count=count, roster_size=count,
                    interaction_failure_count=failures)

    def test_waits_for_recorded_message_and_background_work(self):
        runner = Runner("http://test", poll=0, idle_grace=0)
        states = iter([self.state(), self.state(), self.state(1, False), self.state(1)])
        calls = []
        def request(method, path, payload=None):
            calls.append((method, path, payload))
            return (202, {}) if method == "POST" else (200, next(states))
        runner.request = request
        result = runner.send("Hello")
        self.assertEqual(result["roster_size_after"], 1)
        self.assertEqual(calls[1], ("POST", "/chat/send", {
            "messages": [{"role": "user", "content": "Hello"}]}))
        self.assertEqual(len(calls), 5)

    def test_stops_on_background_failure(self):
        runner = Runner("http://test", poll=0)
        runner.request = lambda *args: (200, self.state(1, failures=1))
        with self.assertRaisesRegex(RuntimeError, "Server task failed"):
            runner.wait(self.state())

    def test_rejects_nonisolated_server(self):
        runner = Runner("http://test")
        runner.request = lambda *args: (200, {**self.state(), "isolated_tools": False})
        with self.assertRaisesRegex(RuntimeError, "isolated"):
            runner.status()


if __name__ == "__main__":
    unittest.main()
