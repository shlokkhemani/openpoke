"""Summarize roster size and scoped input tokens offline."""
import argparse
import json
from pathlib import Path

from .measurement import digest
from .recover_input_tokens import RECOVERY_FILE, apply_recoveries


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def input_token_report(run_dir, initial, run_complete):
    path = run_dir / "application_events.json"
    available = initial.get("token_tracking_version") == 1 and path.exists()
    events = json.loads(path.read_text()) if available else []
    original_events = events
    recovery_path = run_dir / RECOVERY_FILE
    if available and recovery_path.exists():
        events = apply_recoveries(events, json.loads(recovery_path.read_text()))
    counts = {}
    for kind in ("interaction", "embedding"):
        calls = [row for row in events if row.get("event") == "input_tokens" and row.get("kind") == kind]
        values = [row.get("input_tokens") for row in calls]
        known = [value for value in values if isinstance(value, int) and not isinstance(value, bool) and value >= 0]
        missing = len(values) - len(known)
        counts[kind] = {"calls": len(calls), "missing_usage_calls": missing,
                        "recovered_usage_calls": sum(row.get("usage_source") == "generation_metadata" for row in calls),
                        "missing_usage_outcomes": {outcome: sum(row.get("input_tokens") is None
                            and row.get("request_outcome", "unknown") == outcome for row in calls)
                            for outcome in sorted({row.get("request_outcome", "unknown") for row in calls
                                                   if row.get("input_tokens") is None})},
                        "known_input_tokens": sum(known) if available else None,
                        "input_tokens": sum(known) if available and not missing else None}
    mode = initial.get("routing", {}).get("mode")
    included = ("interaction", "embedding") if mode == "shortlist" else ("interaction",)
    final_path = run_dir / "final_snapshot.json"
    coverage = False
    if available and run_complete and final_path.exists():
        final = json.loads(final_path.read_text())
        coverage = (final.get("token_tracking_version") == 1
                    and final.get("metrics_events", [])[:len(initial.get("metrics_events", []))]
                    == initial.get("metrics_events", [])
                    and final.get("metrics_events", [])[len(initial.get("metrics_events", [])):] == original_events)
    complete = coverage and mode in {"full_roster", "shortlist"} and all(
        counts[kind]["input_tokens"] is not None for kind in included)
    return {"available": available, "complete": complete, **counts,
            "total_input_tokens": sum(counts[kind]["input_tokens"] for kind in included) if complete else None}


def build_report(run_dir):
    rows = read_jsonl(run_dir / "run.jsonl")
    start = next(row for row in rows if row["event"] == "start")
    groups = [row for row in rows if row["event"] == "group_completed"]
    evidence = [row for row in rows if row["event"] == "measurement"]
    initial = json.loads((run_dir / "initial_snapshot.json").read_text())
    complete = any(row["event"] == "finished" for row in rows)
    for entry in evidence:
        path = run_dir / entry["evidence_file"]
        if digest(json.loads(path.read_text())) != entry["evidence_sha256"]:
            raise ValueError("Outcome evidence was modified after collection")
    # Fixed inputs and environment must match before comparing measurements.
    signature = digest({"messages": start["messages"], "schedule": start["schedule"],
                        "email_state": initial["email_state"], "triggers": initial["triggers"],
                        "clock_day": initial["status"]["simulated_day"],
                        "clock_time": initial["clock_time"],
                        "prior_conversation": initial["conversation"],
                        "models": initial["models"]})
    return {
        "run_complete": complete, "requested_messages": start["message_count"],
        "completed_messages": groups[-1]["last_index"] if groups else 0,
        "routing": initial.get("routing", {"mode": "unknown"}),
        "tokens": input_token_report(run_dir, initial, complete),
        "roster": {"initial_size": start["initial_status"]["roster_size"],
                   "last_completed_size": groups[-1]["roster_size_after"] if groups
                                          else start["initial_status"]["roster_size"],
                   "growth": [{"through_message": row["last_index"],
                               "size": row["roster_size_after"]} for row in groups]},
        "input_signature": signature,
    }


def compare_reports(baseline, candidate):
    if baseline["input_signature"] != candidate["input_signature"]:
        raise ValueError("Different user inputs, schedules, initial inbox/state, or application models")
    if baseline["roster"]["initial_size"] or candidate["roster"]["initial_size"]:
        raise ValueError("This comparison requires both runs to start with an empty roster")
    roster_complete = baseline["run_complete"] and candidate["run_complete"]
    tokens_complete = baseline["tokens"]["complete"] and candidate["tokens"]["complete"]
    return {"roster_comparison_complete": roster_complete,
            "roster_size_change": candidate["roster"]["last_completed_size"]
                                  - baseline["roster"]["last_completed_size"]
            if roster_complete else None,
            "token_comparison_complete": tokens_complete,
            "input_token_change": candidate["tokens"]["total_input_tokens"]
                                  - baseline["tokens"]["total_input_tokens"]
            if tokens_complete else None,
            "baseline": baseline, "candidate": candidate}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--compare", type=Path, help="Candidate run; first directory is baseline")
    args = parser.parse_args()
    report = build_report(args.run_dir)
    if args.compare:
        report = compare_reports(report, build_report(args.compare))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
