"""Summarize full-roster size offline; preserve outcomes for manual review."""
import argparse
import json
from pathlib import Path

from .measurement import digest


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


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
    return {"roster_comparison_complete": roster_complete,
            "roster_size_change": candidate["roster"]["last_completed_size"]
                                  - baseline["roster"]["last_completed_size"]
            if roster_complete else None,
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
