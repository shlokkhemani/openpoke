"""Deterministic checks over a recorded run folder (see evals/harness/runner.py for the layout)."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

from ..harness.timeexpr import parse_storage, resolve

TIME_TOLERANCE = timedelta(seconds=60)

# Not used for scoring anymore (duplicate and leak checks were dropped from task completion).
LEAK_PATTERNS = [
    r"\b(send_message_to_agent|send_message_to_user|send_draft|delegate\(|find_agents|read_conversation|report_status|createTrigger|updateTrigger|listTriggers|task_email_search)\b",
    r"</?(wait|agent_message|new_user_message|new_agent_message|poke_reply|user_message|conversation_history|agents|agent|active_agents|note|previous_poke_reply|current_time)\b[^>]*>",
    r"\btrigger[ _]?id\b",
]


# ---------------------------------------------------------------------------------------- run data
@dataclass
class RunData:
    folder: Path
    meta: Dict[str, Any]
    steps: List[Dict[str, Any]]
    transcript: List[Dict[str, Any]]
    llm_events: List[Dict[str, Any]]
    _snapshot_cache: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, folder: Path) -> "RunData":
        def read_json(name: str, default: Any) -> Any:
            path = folder / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

        events = []
        calls = folder / "llm_calls.jsonl"
        if calls.exists():
            for line in calls.read_text(encoding="utf-8").splitlines():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
        return cls(folder, read_json("meta.json", {}), read_json("steps.json", []),
                   read_json("transcript.json", []), events)

    @property
    def tz(self) -> str:
        return self.meta.get("timezone", "UTC")

    @property
    def last_step(self) -> int:
        return len(self.steps)

    def step(self, index: int) -> Dict[str, Any]:
        return self.steps[index - 1]

    def snapshot(self, index: Optional[int] = None) -> Dict[str, Any]:
        index = index or self.last_step
        if index in self._snapshot_cache:
            return self._snapshot_cache[index]
        folder = self.folder / "snapshots" / f"step_{index}"
        triggers: List[Dict[str, Any]] = []
        if (folder / "triggers.db").exists():
            conn = sqlite3.connect(folder / "triggers.db")
            conn.row_factory = sqlite3.Row
            try:
                triggers = [dict(row) for row in conn.execute("SELECT * FROM triggers ORDER BY id")]
            except sqlite3.Error:
                triggers = []
            finally:
                conn.close()
        roster: List[str] = []
        if (folder / "roster.json").exists():
            raw = json.loads((folder / "roster.json").read_text(encoding="utf-8") or "[]")
            roster = [item if isinstance(item, str) else item.get("name", "") for item in raw]
        memory = (folder / "poke_working_memory.log").read_text(encoding="utf-8") \
            if (folder / "poke_working_memory.log").exists() else ""
        exec_logs = "\n".join(p.read_text(encoding="utf-8") for p in sorted((folder / "execution_agents").rglob("*.log"))) \
            if (folder / "execution_agents").exists() else ""
        snap = {"triggers": triggers, "roster": [r for r in roster if r], "memory": memory, "exec_logs": exec_logs}
        self._snapshot_cache[index] = snap
        return snap

    def assistant_messages(self, step_selector: Any = "all") -> List[str]:
        steps = self._select_steps(step_selector)
        return [m.get("content", "") for m in self.transcript
                if m.get("role") == "assistant" and m.get("step") in steps]

    def _select_steps(self, selector: Any) -> set:
        if selector in (None, "all"):
            return set(range(1, self.last_step + 1))
        if selector == "last":
            return {self.last_step}
        if selector == "fire":
            return {s["step"] for s in self.steps if s.get("kind") == "fire"}
        return {int(selector)}

    def reference_time(self, relative_to: Optional[str]) -> datetime:
        if relative_to and relative_to.startswith("step:"):
            value = relative_to.split(":", 1)[1]
            index = self.last_step if value == "last" else int(value)
            return datetime.fromtimestamp(self.step(index)["started_at"], tz=timezone.utc)
        if relative_to == "fire":
            fires = [s for s in self.steps if s.get("kind") == "fire"]
            if fires:
                return datetime.fromtimestamp(fires[-1]["started_at"], tz=timezone.utc)
        return datetime.fromisoformat(self.meta["run_start"])


@dataclass
class CheckResult:
    type: str
    passed: bool
    detail: str
    value: Optional[float] = None
    metric: Optional[str] = None


# ---------------------------------------------------------------------------------------- helpers
def _filter(rows: List[Dict[str, Any]], where: Optional[Dict[str, Any]], status: Any) -> List[Dict[str, Any]]:
    where = where or {}
    out = []
    statuses = [status] if isinstance(status, str) else status
    for row in rows:
        if where.get("payload") and not re.search(where["payload"], row.get("payload") or "", re.I):
            continue
        if where.get("recurrence") and not re.search(where["recurrence"], row.get("recurrence_rule") or "", re.I):
            continue
        if statuses and row.get("status") not in statuses:
            continue
        out.append(row)
    return out


def _local(ts: Optional[str], tz: str) -> Optional[datetime]:
    parsed = parse_storage(ts)
    return parsed.astimezone(ZoneInfo(tz)) if parsed else None


def _fire_times_of_day(row: Dict[str, Any], tz: str, start: datetime, days: int = 7) -> set:
    zone = ZoneInfo(tz)
    if row.get("recurrence_rule"):
        try:
            rule = rrulestr(row["recurrence_rule"])
            occurrences = rule.between(start.astimezone(zone), start.astimezone(zone) + timedelta(days=days), inc=True)
            return {occ.astimezone(zone).strftime("%H:%M") for occ in occurrences}
        except Exception:
            pass
    local = _local(row.get("next_trigger"), tz)
    return {local.strftime("%H:%M")} if local else set()


def _contains(text: str, item: str) -> bool:
    """Item matches if any '|'-separated alternative is a case-insensitive substring."""
    lowered = text.lower()
    return any(alt.strip().lower() in lowered for alt in item.split("|"))


def _count_ok(n: int, spec: Dict[str, Any]) -> Tuple[bool, str]:
    if "equals" in spec and n != spec["equals"]:
        return False, f"count {n} != {spec['equals']}"
    if "min" in spec and n < spec["min"]:
        return False, f"count {n} < {spec['min']}"
    if "max" in spec and n > spec["max"]:
        return False, f"count {n} > {spec['max']}"
    return True, f"count {n}"


# ---------------------------------------------------------------------------------------- checks
def check_trigger_count(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    rows = _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), spec.get("status"))
    ok, detail = _count_ok(len(rows), spec)
    return CheckResult("trigger_count", ok, detail)


def check_trigger_time(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    rows = _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), spec.get("status", "active"))
    expected = resolve(spec["expect"], run.reference_time(spec.get("relative_to")), run.tz)
    tolerance = timedelta(minutes=spec["tolerance_min"]) if "tolerance_min" in spec else TIME_TOLERANCE
    actual = [parse_storage(r.get("next_trigger")) for r in rows]
    ok = any(a is not None and abs(a - expected) <= tolerance for a in actual)
    shown = [a.astimezone(expected.tzinfo).isoformat() if a else None for a in actual]
    return CheckResult("trigger_time", ok, f"expected {expected.isoformat()}, got {shown}")


def check_trigger_window(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    """At least one matching trigger, and all of them due after the step started and no later than `before`."""
    rows = _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), spec.get("status", "active"))
    start = run.reference_time(spec.get("relative_to"))
    latest = resolve(spec["before"], start, run.tz) + TIME_TOLERANCE
    times = [parse_storage(r.get("next_trigger")) for r in rows]
    ok = bool(times) and all(t is not None and start <= t <= latest for t in times)
    shown = [t.astimezone(latest.tzinfo).isoformat() if t else None for t in times]
    return CheckResult("trigger_window", ok, f"due times {shown}, allowed until {latest.isoformat()}")


def check_fire_times_of_day(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    rows = _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), spec.get("status", "active"))
    start = run.reference_time(spec.get("relative_to"))
    times: set = set()
    for row in rows:
        times |= _fire_times_of_day(row, run.tz, start)
    expected = set(spec["expect"])
    return CheckResult("fire_times_of_day", times == expected, f"expected {sorted(expected)}, got {sorted(times)}")


def check_field_contains(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    rows = _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), spec.get("status", "active"))
    fld = spec.get("field", "recurrence_rule")
    def row_ok(row: Dict[str, Any]) -> bool:
        value = (row.get(fld) or "").upper()
        all_ok = all(item.upper() in value for item in spec.get("all", []))
        any_ok = not spec.get("any") or any(item.upper() in value for item in spec["any"])
        return all_ok and any_ok
    mode = spec.get("mode", "any")
    hits = [row_ok(r) for r in rows]
    ok = bool(rows) and (all(hits) if mode == "all" else any(hits))
    return CheckResult("field_contains", ok, f"{fld} values: {[r.get(fld) for r in rows]}")


def check_field_empty(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    rows = _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), spec.get("status", "active"))
    fld = spec.get("field", "recurrence_rule")
    ok = bool(rows) and all(not (r.get(fld) or "").strip() for r in rows)
    return CheckResult("field_empty", ok, f"{fld} values: {[r.get(fld) for r in rows]}")


def check_payload_contains_all(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    rows = _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), spec.get("status"))
    text = "\n".join(r.get("payload") or "" for r in rows)
    items = spec["items"]
    found = [item for item in items if _contains(text, item)]
    ratio = len(found) / len(items) if items else 1.0
    missing = [item for item in items if item not in found]
    return CheckResult("payload_contains_all", bool(rows) and not missing,
                       f"{len(found)}/{len(items)} found; missing {missing}", ratio, spec.get("metric"))


def check_same_agent(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    rows = _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), spec.get("status"))
    agents = {r.get("agent_name") for r in rows}
    return CheckResult("same_agent", len(rows) > 0 and len(agents) == 1, f"agents: {sorted(a or '' for a in agents)}")


def check_agent_unchanged(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    before = {r["id"]: r.get("agent_name") for r in _filter(run.snapshot(spec["from_step"])["triggers"], spec.get("where"), None)}
    after = {r["id"]: r.get("agent_name") for r in _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), spec.get("status", "active"))}
    owners_before = set(before.values())
    ok = bool(after) and bool(owners_before) and set(after.values()) <= owners_before
    return CheckResult("agent_unchanged", ok, f"before {sorted(owners_before)}, after {sorted(set(after.values()))}")


def check_status_in(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    rows = _filter(run.snapshot(spec.get("after_step"))["triggers"], spec.get("where"), None)
    ok = bool(rows) and all(r.get("status") in spec["statuses"] for r in rows)
    return CheckResult("status_in", ok, f"statuses: {[r.get('status') for r in rows]}")


def check_reply_contains(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    text = "\n".join(run.assistant_messages(spec.get("step", "all")))
    all_items = spec.get("all", [])
    found = [i for i in all_items if _contains(text, i)]
    missing = [i for i in all_items if i not in found]
    any_ok = not spec.get("any") or any(_contains(text, i) for i in spec["any"])
    present_forbidden = [i for i in spec.get("none", []) if _contains(text, i)]
    ok = not missing and any_ok and not present_forbidden
    ratio = len(found) / len(all_items) if all_items else None
    return CheckResult("reply_contains", ok,
                       f"missing {missing}; any_ok={any_ok}; forbidden present {present_forbidden}", ratio, spec.get("metric"))


def check_message_count(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    n = len(run.assistant_messages(spec.get("step", "all")))
    ok, detail = _count_ok(n, spec)
    return CheckResult("message_count", ok, detail)


def check_agents_created(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    n = len(run.snapshot(spec.get("after_step"))["roster"])
    ok, detail = _count_ok(n, spec)
    return CheckResult("agents_created", ok, detail)


def check_no_execution_calls(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    from .metrics import role_of

    n = sum(1 for e in run.llm_events if e.get("event") == "start" and role_of(e) == "execution")
    return CheckResult("no_execution_calls", n == 0, f"{n} execution calls")


def check_summary_exists(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    memory = run.snapshot(spec.get("after_step"))["memory"]
    match = re.search(r"<conversation_summary>(.*?)</conversation_summary>", memory, re.S)
    ok = bool(match and match.group(1).strip())
    return CheckResult("summary_exists", ok, "summary present" if ok else "no summary")


def check_none_due_soon(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    """No trigger fired immediately or is due within `minutes` of the step ending."""
    index = spec.get("after_step") or run.last_step
    rows = run.snapshot(index)["triggers"]
    step_end = datetime.fromtimestamp(run.step(index)["done_at"], tz=timezone.utc)
    limit = step_end + timedelta(minutes=spec.get("minutes", 1))
    bad = [r for r in rows if r.get("status") == "completed"
           or (r.get("next_trigger") and parse_storage(r["next_trigger"]) <= limit)]
    return CheckResult("none_due_soon", not bad, f"due/fired immediately: {[r.get('payload') for r in bad]}")


def check_any_of(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    results = [run_check(run, sub) for sub in spec["checks"]]
    return CheckResult("any_of", any(r.passed for r in results), " | ".join(f"{r.type}:{r.detail}" for r in results))


def check_all_of(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    results = [run_check(run, sub) for sub in spec["checks"]]
    return CheckResult("all_of", all(r.passed for r in results), " & ".join(f"{r.type}:{r.detail}" for r in results))


CHECKS: Dict[str, Callable[[RunData, Dict[str, Any]], CheckResult]] = {
    "trigger_count": check_trigger_count,
    "trigger_time": check_trigger_time,
    "fire_times_of_day": check_fire_times_of_day,
    "trigger_window": check_trigger_window,
    "field_contains": check_field_contains,
    "field_empty": check_field_empty,
    "payload_contains_all": check_payload_contains_all,
    "same_agent": check_same_agent,
    "agent_unchanged": check_agent_unchanged,
    "status_in": check_status_in,
    "reply_contains": check_reply_contains,
    "message_count": check_message_count,
    "agents_created": check_agents_created,
    "no_execution_calls": check_no_execution_calls,
    "summary_exists": check_summary_exists,
    "none_due_soon": check_none_due_soon,
    "any_of": check_any_of,
    "all_of": check_all_of,
}


def run_check(run: RunData, spec: Dict[str, Any]) -> CheckResult:
    fn = CHECKS.get(spec.get("type", ""))
    if fn is None:
        return CheckResult(spec.get("type", "?"), False, "unknown check type")
    try:
        return fn(run, spec)
    except Exception as exc:  # a broken check must fail loudly, not crash scoring
        return CheckResult(spec.get("type", "?"), False, f"error: {exc}")


# ---------------------------------------------------------------------------------------- always-on
def always_on_checks(run: RunData) -> List[CheckResult]:
    results: List[CheckResult] = []

    timed_out = [s["step"] for s in run.steps if s.get("timed_out")]
    results.append(CheckResult("no_timeouts", not timed_out, f"timed out steps: {timed_out}"))

    user_steps = [s["step"] for s in run.steps if s.get("kind") == "user"]
    unanswered = [i for i in user_steps if not run.assistant_messages(i)]
    results.append(CheckResult("every_turn_replied", not unanswered, f"unanswered steps: {unanswered}"))

    return results


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """Static validation used by --dry-run."""
    errors = []
    kind = spec.get("type")
    if kind not in CHECKS:
        errors.append(f"unknown check type {kind!r}")
    for sub in spec.get("checks", []) if kind in ("any_of", "all_of") else []:
        errors.extend(validate_spec(sub))
    return errors


__all__ = ["RunData", "CheckResult", "run_check", "always_on_checks", "validate_spec", "CHECKS"]
