"""A tiny synthetic run folder (records, grades, summary, errors, transcripts) for eval-browsing tests."""
import json
from pathlib import Path

SUMMARY = {"purpose": "synthetic", "date_utc": "2026-11-07T12:00:00Z", "run_folder": "20261107T120000Z-synthetic",
           "model": "test/model-1"}


def grade_row(case, mode, n, idx, passed, kind="dispatch", flags=(), category="cat-a"):
    return {"case_id": case, "mode": mode, "n": n, "run_idx": idx, "category": category, "graded_as": mode,
            "passed": passed, "outcome_kind": kind, "person_ok": True, "clarify_named_ok": None,
            "set_recall": 1.0, "set_precision": 0.5, "structural": False, "flags": list(flags),
            "slots_filled": 2, "slots_total": 3}


def record_row(case, mode, n, idx, reused_from=None, category="cat-a"):
    return {"case_id": case, "mode": mode, "n": n, "run_idx": idx, "calls": [{"name": "send_message_to_agent"}],
            "user_messages": [], "final_text": "done", "latency_s": 1.5, "round_trips": 2, "error": None,
            "model": "test/model-1", "category": category, "reused_from": reused_from}


def transcript(case, mode, n, idx, marker, reused_from=None):
    return {"case_id": case, "mode": mode, "n": n, "run_idx": idx, "model": "test/model-1", "error": None,
            "reused_from": reused_from, "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": f"please do {marker}"},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"type": "function", "index": 0, "id": f"call_{marker}",
                     "function": {"name": "send_message_to_agent",
                                  "arguments": json.dumps({"agent_name": "Mailer", "instructions": marker})}}]},
                {"role": "tool", "tool_call_id": f"call_{marker}", "content": "ok"},
                {"role": "assistant", "content": "done"}]}


def write_run(root: Path, rows, name="20261107T120000Z-synthetic", errors=(), missing=()):
    """rows: (case, mode, n, idx, passed, kind, flags, reused_from). Returns the run folder."""
    run = root / name
    (run / "transcripts").mkdir(parents=True)
    grades, records = [], []
    for case, mode, n, idx, passed, kind, flags, reused in rows:
        grades.append(grade_row(case, mode, n, idx, passed, kind, flags))
        records.append(record_row(case, mode, n, idx, reused))
        src = reused or mode
        f = run / "transcripts" / f"{case}-{src}-{n}-{idx}.json"
        if (case, src, n, idx) not in missing and not f.exists():
            f.write_text(json.dumps(transcript(case, src, n, idx, f"{case}-{src}", reused)))
    for name_, rs in (("grades", grades), ("records", records), ("errors", list(errors))):
        (run / f"{name_}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rs))
    (run / "summary.json").write_text(json.dumps({**SUMMARY, "run_folder": name}))
    return run
