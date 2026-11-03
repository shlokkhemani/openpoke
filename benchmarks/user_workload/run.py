"""Send a fixed sequence to OpenPoke and measure natural roster growth."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from .__main__ import ROOT, load_messages
from .schedule import load_groups


class Runner:
    def __init__(self, base_url, timeout=600, poll=1, idle_grace=2):
        self.base_url = base_url.rstrip("/")
        self.timeout, self.poll, self.idle_grace = timeout, poll, idle_grace

    def request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        req = Request(self.base_url + path, data=body, method=method,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}

    def status(self):
        _, state = self.request("GET", "/benchmark/status")
        if not all(state.get(key) is True for key in
                   ("benchmark_mode", "isolated_data_dir", "isolated_tools")):
            raise RuntimeError("An isolated server with /benchmark/status is required")
        return state

    def wait(self, before, message_count=1):
        deadline, idle_since = time.monotonic() + self.timeout, None
        while time.monotonic() < deadline:
            state = self.status()
            if state.get("interaction_failure_count", 0) > before.get("interaction_failure_count", 0):
                raise RuntimeError(f"Server task failed: {state.get('failures', [])}")
            expected = before["user_message_count"] + message_count
            if state["user_message_count"] > expected:
                raise RuntimeError("Concurrent user messages detected; use a dedicated server")
            if state["user_message_count"] == expected and state.get("idle") is True:
                if idle_since is None:
                    idle_since = time.monotonic()
                if time.monotonic() - idle_since >= self.idle_grace:
                    return state
            else:
                idle_since = None
            time.sleep(self.poll)
        raise TimeoutError("Turn timed out; inspect server before continuing")

    def send(self, message):
        before = self.status()
        if not before.get("idle"):
            raise RuntimeError("Server is busy")
        started = time.monotonic()
        code, _ = self.request("POST", "/chat/send", {
            "messages": [{"role": "user", "content": message}]})
        if code != 202:
            raise RuntimeError(f"Expected HTTP 202, received {code}")
        after = self.wait(before)
        return {"user_message": message, "roster_size_before": before["roster_size"],
                "roster_size_after": after["roster_size"],
                "duration_seconds": round(time.monotonic() - started, 3)}

    def send_group(self, messages, offsets, start_index, record):
        before = self.status()
        if not before.get("idle"):
            raise RuntimeError("Server is busy before message group")
        started = time.monotonic()
        observations = []
        for position, (message, offset) in enumerate(zip(messages, offsets)):
            time.sleep(max(0, started + offset - time.monotonic()))
            state = self.status()
            if state.get("interaction_failure_count", 0) > before.get("interaction_failure_count", 0):
                raise RuntimeError(f"Server task failed: {state.get('failures', [])}")
            if state["user_message_count"] > before["user_message_count"] + position:
                raise RuntimeError("Unexpected concurrent user messages")
            observed = {
                "event": "submitting", "index": start_index + position,
                "user_message": message, "scheduled_offset_seconds": offset,
                "actual_offset_seconds": round(time.monotonic() - started, 3),
                "earlier_work_pending": position > 0 and state.get("idle") is False,
                "active_interactions": state.get("active_interactions", 0),
                "pending_execution_count": len(state.get("pending_executions", [])),
            }
            record(observed)
            code, _ = self.request("POST", "/chat/send", {
                "messages": [{"role": "user", "content": message}]})
            if code != 202:
                raise RuntimeError(f"Expected HTTP 202, received {code}")
            record({"event": "accepted", "index": start_index + position})
            observations.append(observed)
        after = self.wait(before, len(messages))
        result = {
            "event": "group_completed", "first_index": start_index,
            "last_index": start_index + len(messages) - 1,
            "roster_size_before": before["roster_size"],
            "roster_size_after": after["roster_size"],
            "duration_seconds": round(time.monotonic() - started, 3),
            "observed_overlapping_messages": sum(o["earlier_work_pending"] for o in observations),
        }
        record(result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8011/api/v1")
    parser.add_argument("--messages", type=Path, default=ROOT / "setup_messages.json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--turn-timeout", type=float, default=600)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--schedule", type=Path, help="Timing file; defaults to the bundled schedule for bundled messages")
    parser.add_argument("--allow-existing-state", action="store_true")
    parser.add_argument("--live", action="store_true", help="Send messages; incurs model API costs")
    args = parser.parse_args()
    if args.turn_timeout <= 0 or (args.limit is not None and args.limit < 1):
        parser.error("Timeout and limit must be positive")
    messages = load_messages(args.messages)
    schedule = args.schedule
    if schedule is None:
        for filename, timing in (("setup_messages.json", "setup_schedule.json"),
                                 ("test_messages.json", "test_schedule.json")):
            if args.messages.resolve() == (ROOT / filename).resolve():
                schedule = ROOT / timing
    groups = load_groups(schedule, len(messages))
    if args.limit:
        # Keep complete bursts: silently cutting one changes the scenario.
        if any(start <= args.limit < start + len(offsets) - 1 for start, offsets in groups):
            parser.error("--limit cuts through an overlapping group; choose a group boundary")
        messages = messages[:args.limit]
        groups = [(start, offsets) for start, offsets in groups if start <= len(messages)]
    if not args.live:
        print(f"Preview: {len(messages)} messages from {args.messages}")
        print(f"Timing: {sum(len(o) > 1 for _, o in groups)} overlapping groups; schedule: {schedule}")
        print(f"Destination: {args.base_url}; add --live to send. No requests made.")
        return
    runner = Runner(args.base_url, args.turn_timeout)
    initial = runner.status()
    if not initial.get("idle"):
        parser.error("Server is busy")
    if not args.allow_existing_state and (initial["roster_size"] or initial["user_message_count"]):
        parser.error("Use fresh isolated state, or explicitly --allow-existing-state")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output_dir or ROOT / "results" / stamp
    output.mkdir(parents=True, exist_ok=True)
    with (output / "run.jsonl").open("x", encoding="utf-8") as journal:
        def record(event):
            journal.write(json.dumps(event) + "\n")
            journal.flush()
        record({"event": "start", "source": str(args.messages.resolve()),
                "message_count": len(messages), "initial_status": initial,
                "schedule": json.loads(schedule.read_text()) if schedule else None,
                "messages": messages})
        for index, offsets in groups:
            try:
                result = runner.send_group(messages[index - 1:index - 1 + len(offsets)],
                                           offsets, index, record)
            except Exception as exc:
                record({"event": "error", "index": index, "error": str(exc)})
                raise
            print(f"{result['last_index']}/{len(messages)}: roster {result['roster_size_before']} -> "
                  f"{result['roster_size_after']}; overlapping arrivals: "
                  f"{result['observed_overlapping_messages']}", flush=True)
        final = runner.status()
        record({"event": "finished", "final_status": final})
    print(f"Completed {len(messages)} messages; roster: {final['roster_size']} agents.")
    print(f"Run log: {output / 'run.jsonl'}")


if __name__ == "__main__":
    main()
