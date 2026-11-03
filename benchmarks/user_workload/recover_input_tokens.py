"""Recover missing interaction input usage via metadata GETs, never model calls."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .measurement import digest

RECOVERY_FILE = "input-token-recovery.json"


def valid_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def apply_recoveries(events, recovery):
    """Return copies; keep the original ledger unchanged and reject stale sidecars."""
    if recovery.get("version") != 1 or recovery.get("events_sha256") != digest(events):
        raise ValueError("Input-token recovery does not match saved events")
    result = [dict(row) for row in events]
    seen = set()
    for entry in recovery["recoveries"]:
        index = entry["event_index"]
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(events) or index in seen:
            raise ValueError("Duplicate or unknown token recovery event")
        seen.add(index)
        original = events[index]
        if (original.get("event") != "input_tokens" or original.get("kind") != "interaction"
                or valid_count(original.get("input_tokens"))
                or original.get("request_outcome") != "success"
                or not original.get("response_id")
                or entry.get("response_id") != original["response_id"]
                or entry.get("model") != original.get("model")):
            raise ValueError("Input-token recovery has different request identity or scope")
        if entry["status"] == "recovered":
            value = entry.get("native_tokens_prompt")
            if not valid_count(value):
                raise ValueError("Recovery requires a provider-native input count")
            result[index].update(input_tokens=value, usage_source="generation_metadata")
        elif entry["status"] != "unavailable":
            raise ValueError("Unknown token recovery status")
    return result


def recover_events(events, fetch, previous=None):
    previous_entries = {}
    if previous is not None:
        apply_recoveries(events, previous)
        previous_entries = {entry["event_index"]: entry for entry in previous["recoveries"]}
    recovered = []
    for index, event in enumerate(events):
        if (event.get("event") != "input_tokens" or event.get("kind") != "interaction"
                or valid_count(event.get("input_tokens")) or event.get("request_outcome") != "success"
                or not isinstance(event.get("response_id"), str) or not event["response_id"]):
            continue
        old = previous_entries.get(index)
        if old and old["status"] == "recovered":
            recovered.append(old)
            continue
        entry = dict(event_index=index, response_id=event["response_id"], model=event["model"], status="unavailable")
        try:
            metadata = fetch(event["response_id"])["data"]
            if metadata.get("id") != event["response_id"] or metadata.get("model") != event["model"]:
                raise ValueError("Generation metadata has different ID or model")
            value = metadata.get("native_tokens_prompt")
            if valid_count(value):
                entry.update(status="recovered", native_tokens_prompt=value)
            else:
                entry["reason"] = "Provider-native input count unavailable"
        except Exception as exc:
            # A failed metadata lookup never reruns a paid generation or fabricates zero.
            entry["reason"] = type(exc).__name__
        recovered.append(entry)
    return dict(version=1, events_sha256=digest(events), recoveries=recovered)


def fetch_generation(response_id, key):
    request = Request("https://openrouter.ai/api/v1/generation?" + urlencode({"id": response_id}),
                      headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def save_recoveries(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--fetch", action="store_true", help="GET usage metadata; no model generation calls")
    args = parser.parse_args()
    events = json.loads((args.run_dir / "application_events.json").read_text())
    path = args.run_dir / RECOVERY_FILE
    previous = json.loads(path.read_text()) if path.exists() else None
    effective = apply_recoveries(events, previous) if previous is not None else events
    missing = [row for row in effective if row.get("event") == "input_tokens" and not valid_count(row.get("input_tokens"))]
    eligible = [row for row in missing if row.get("kind") == "interaction"
                and row.get("request_outcome") == "success" and row.get("response_id")]
    print(f"Missing input counts: {len(missing)}; eligible metadata lookups: {len(eligible)}")
    if not args.fetch or not eligible:
        print("No requests made. Use --fetch for eligible metadata lookups.")
        return
    from server.config import get_settings
    key = get_settings().openrouter_api_key
    if not key:
        parser.error("OPENROUTER_API_KEY is missing")
    result = recover_events(events, lambda identifier: fetch_generation(identifier, key), previous)
    apply_recoveries(events, result)
    save_recoveries(path, result)
    print(f"Recovered: {sum(row['status'] == 'recovered' for row in result['recoveries'])}; saved {path}")


if __name__ == "__main__":
    main()
