"""Usage-metadata recovery without inference or live API calls."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from .recover_input_tokens import (RECOVERY_FILE, apply_recoveries, fetch_generation,
                                  recover_events, save_recoveries)
from .report import input_token_report


def missing_event(**changes):
    return dict(dict(event="input_tokens", kind="interaction", model="chat-model",
                     response_id="gen-123", request_outcome="success", input_tokens=None), **changes)


def metadata(**changes):
    return {"data": dict(dict(id="gen-123", model="chat-model", native_tokens_prompt=42,
                              tokens_prompt=999, native_tokens_completion=80), **changes)}


class RecoveryTests(unittest.TestCase):
    def test_native_input_recovery_preserves_evidence_and_skips_previously_recovered_calls(self):
        events = [missing_event()]
        original = copy.deepcopy(events)
        fetch = Mock(return_value=metadata())
        recovery = recover_events(events, fetch)
        fetch.assert_called_once_with("gen-123")
        self.assertEqual(apply_recoveries(events, recovery)[0]["input_tokens"], 42)
        self.assertEqual(events, original)
        self.assertNotIn("native_tokens_completion", json.dumps(recovery))
        fetch.reset_mock()
        self.assertEqual(recover_events(events, fetch, recovery), recovery)
        fetch.assert_not_called()

    def test_non_native_count_or_lookup_failure_remains_unknown(self):
        for fetch in [Mock(return_value=metadata(native_tokens_prompt=None)),
                      Mock(side_effect=TimeoutError), Mock(return_value=metadata(id="different")),
                      Mock(return_value=metadata(model="other")), Mock(return_value=metadata(native_tokens_prompt=True))]:
            with self.subTest(fetch=fetch):
                events = [missing_event()]
                recovery = recover_events(events, fetch)
                self.assertEqual(recovery["recoveries"][0]["status"], "unavailable")
                self.assertIsNone(apply_recoveries(events, recovery)[0]["input_tokens"])
                self.assertEqual(fetch.call_count, 1)

    def test_no_lookup_without_id_or_after_failure_or_for_embeddings_or_known_counts(self):
        events = [missing_event(response_id=None), missing_event(request_outcome="transport_error"),
                  missing_event(request_outcome="http_error"), missing_event(kind="embedding"),
                  missing_event(input_tokens=0)]
        fetch = Mock()
        self.assertEqual(recover_events(events, fetch)["recoveries"], [])
        fetch.assert_not_called()

    def test_rejects_stale_duplicate_and_mismatched_recovery(self):
        events = [missing_event()]
        recovery = recover_events(events, Mock(return_value=metadata()))
        with self.assertRaises(ValueError):
            apply_recoveries([missing_event(response_id="different")], recovery)
        for changes in ({"response_id": "other"}, {"event_index": 4}, {"model": "other"},
                        {"native_tokens_prompt": -1}):
            bad = copy.deepcopy(recovery)
            bad["recoveries"][0].update(changes)
            with self.assertRaises(ValueError):
                apply_recoveries(events, bad)
        recovery["recoveries"] *= 2
        with self.assertRaises(ValueError):
            apply_recoveries(events, recovery)

    def test_report_uses_recovery_and_keeps_original_ledger_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = [missing_event()]
            initial = dict(token_tracking_version=1, metrics_events=[], routing={"mode": "full_roster"})
            path = root / "application_events.json"
            path.write_text(json.dumps(events))
            original = path.read_bytes()
            (root / "final_snapshot.json").write_text(json.dumps(dict(token_tracking_version=1, metrics_events=events)))
            self.assertFalse(input_token_report(root, initial, True)["complete"])
            save_recoveries(root / RECOVERY_FILE, recover_events(events, Mock(return_value=metadata())))
            result = input_token_report(root, initial, True)
            self.assertTrue(result["complete"])
            self.assertEqual(result["total_input_tokens"], 42)
            self.assertEqual(result["interaction"]["recovered_usage_calls"], 1)
            self.assertEqual(path.read_bytes(), original)

    def test_metadata_request_is_get_not_generation(self):
        with patch("benchmarks.user_workload.recover_input_tokens.urlopen",
                   return_value=io.BytesIO(json.dumps(metadata()).encode())) as request:
            self.assertEqual(fetch_generation("gen-123", "fake"), metadata())
        sent = request.call_args.args[0]
        self.assertEqual(sent.get_method(), "GET")
        self.assertEqual(sent.full_url, "https://openrouter.ai/api/v1/generation?id=gen-123")
        self.assertIsNone(sent.data)
