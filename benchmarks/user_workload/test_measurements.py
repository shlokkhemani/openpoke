"""Saved evidence and roster-report tests without model calls."""
import json
import os
import tempfile
import unittest
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from server.benchmark_events import append_event, read_events
from .measurement import digest, make_evidence
from .report import build_report, compare_reports
from .run import Runner, main as run_main


def snapshot(conversation=None, events=None):
    return {"conversation": conversation or [], "metrics_events": events or [],
            "triggers": [], "email_state": {"inbox": [], "drafts": []},
            "status": {"simulated_day": 0, "roster_size": 0},
            "clock_time": "2026-01-01T09:00:00+00:00", "models": {"interaction": "test"}}


def evidence():
    return make_evidence(snapshot(), snapshot([
        {"type": "user_message", "content": "Draft GB-88 for $2,400. Don't send it."},
        {"type": "poke_reply", "content": "Draft: GB-88, $2,400."},
    ]), ["Draft GB-88 for $2,400. Don't send it."], 1)


class EvidenceLogTests(unittest.TestCase):
    def test_durable_threadsafe_email_action_log(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OPENPOKE_BENCHMARK_MODE": "1", "OPENPOKE_DATA_DIR": directory,
        }):
            def write(index):
                append_event({"event": "email_action", "index": index})
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(write, range(20)))
            self.assertEqual(sorted(e["index"] for e in read_events()), list(range(20)))

    def test_no_telemetry_outside_benchmark_mode(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OPENPOKE_BENCHMARK_MODE": "0", "OPENPOKE_DATA_DIR": directory,
        }):
            append_event({"event": "test"})
            self.assertEqual(list(Path(directory).iterdir()), [])


class EvidenceTests(unittest.TestCase):


    def test_reset_evidence_is_rejected(self):
        before = snapshot([{ "type": "user_message", "content": "earlier"}])
        with self.assertRaises(ValueError):
            make_evidence(before, snapshot(), ["current"], 2)


class ReportTests(unittest.TestCase):

    def test_reports_ignore_archived_automatic_verdicts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_run(directory)
            expected = build_report(root)
            (root / "quality.jsonl").write_text("invalid archived judge output")
            self.assertEqual(build_report(root), expected)
            self.assertNotIn("quality", expected)
            self.assertNotIn("quality_pass_rate_change", compare_reports(expected, expected))

    def test_roster_change_is_candidate_minus_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = build_report(self.write_run(directory))
            for size in (0, 1, 4):
                candidate = {**baseline, "roster": {**baseline["roster"], "last_completed_size": size}}
                comparison = compare_reports(baseline, candidate)
                self.assertTrue(comparison["roster_comparison_complete"])
                self.assertEqual(comparison["roster_size_change"], size - 1)


    def test_runner_saves_outcomes_and_report_end_to_end_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "messages.json"
            message = "Draft GB-88 for $2,400. Don't send it."
            source.write_text(json.dumps([message]))
            conversation, events = [], []
            def status():
                return dict(benchmark_mode=True, isolated_data_dir=True, isolated_tools=True,
                            idle=True, user_message_count=len(conversation) // 2,
                            roster_size=len(conversation) // 2, interaction_failure_count=0)
            def request(_self, method, path, payload=None):
                if path == "/chat/send":
                    conversation.extend([{"type": "user_message", "content": payload["messages"][0]["content"]},
                                         {"type": "poke_reply", "content": "Draft: GB-88, $2,400."}])
                    events.append({"event": "email_action", "tool": "GMAIL_CREATE_EMAIL_DRAFT",
                                   "succeeded": True})
                    events.append({"event": "input_tokens", "kind": "interaction", "input_tokens": 42})
                    return 202, {}
                if path == "/benchmark/status":
                    return 200, status()
                if path == "/benchmark/snapshot":
                    value = snapshot(conversation, events)
                    value.update(metrics_version=1, token_tracking_version=1,
                                 routing={"mode": "full_roster"},
                                 status={**status(), "simulated_day": 0})
                    return 200, json.loads(json.dumps(value))
                raise AssertionError(path)
            output = root / "result"
            with patch("sys.argv", ["run", "--live", "--messages", str(source), "--output-dir", str(output)]), \
                 patch.object(Runner, "request", new=request), \
                 patch.object(Runner, "wait", side_effect=lambda before, count: status()), \
                 patch("sys.stdout", new_callable=io.StringIO):
                run_main()
            report = build_report(output)
            self.assertEqual(report["completed_messages"], 1)
            self.assertEqual(report["tokens"]["total_input_tokens"], 42)
            self.assertTrue(report["tokens"]["complete"])
            packet = json.loads((output / "evidence/0001.json").read_text())
            self.assertEqual(packet["requests"], [message])
            self.assertEqual(packet["current_conversation"][-1]["content"], "Draft: GB-88, $2,400.")

    def write_run(self, directory):
        root = Path(directory)
        (root / "evidence").mkdir()
        packet = evidence()
        (root / "initial_snapshot.json").write_text(json.dumps(snapshot()))
        (root / "evidence/0001.json").write_text(json.dumps(packet))
        rows = [
            {"event": "start", "messages": packet["requests"], "schedule": None,
             "message_count": 1, "initial_status": {"roster_size": 0}},
            {"event": "group_completed", "first_index": 1, "last_index": 1, "roster_size_after": 1},
            {"event": "measurement", "first_index": 1, "last_index": 1,
             "evidence_file": "evidence/0001.json", "evidence_sha256": digest(packet)},
            {"event": "finished"},
        ]
        (root / "run.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        (root / "application_events.json").write_text(json.dumps([
            {"event": "email_action", "tool": "GMAIL_CREATE_EMAIL_DRAFT", "succeeded": True}]))
        return root


    def test_comparison_rejects_different_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = build_report(self.write_run(directory))
            candidate = {**baseline, "input_signature": "different"}
            with self.assertRaises(ValueError):
                compare_reports(baseline, candidate)

    def test_modified_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_run(directory)
            (root / "evidence/0001.json").write_text(json.dumps({"tampered": True}))
            with self.assertRaises(ValueError):
                build_report(root)

    def test_partial_run_does_not_claim_complete_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_run(directory)
            rows = [r for r in (root / "run.jsonl").read_text().splitlines()
                    if json.loads(r)["event"] != "finished"]
            (root / "run.jsonl").write_text("\n".join(rows))
            report = build_report(root)
            self.assertIsNone(compare_reports(report, report)["roster_size_change"])
