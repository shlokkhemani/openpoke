"""Play one scenario against one OpenPoke checkout and record everything into a run folder.

Run folder layout:
    meta.json          case id, version, timezone, run start, config
    steps.json         one entry per step (send/fire times, completion, timeout)
    transcript.json    user-visible messages with harness-observed arrival time and step index
    llm_calls.jsonl    start/end events for every LLM call (from serve.py)
    snapshots/step_N/  triggers.db, roster.json, poke_working_memory.log, execution_agents/ after step N
    server.log         server stdout/stderr
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx

SERVE_SCRIPT = Path(__file__).with_name("serve.py")
QUIET_SECONDS = 5.0
STUCK_CALL_SECONDS = 120.0
TURN_TIMEOUT_SECONDS = 180.0
FIRE_TIMEOUT_SECONDS = 180.0
WAIT_FIRE_TIMEOUT_SECONDS = 600.0
POLL_SECONDS = 0.5


@dataclass
class RunOptions:
    python: str
    env_file: Path
    timezone: str = "America/Los_Angeles"
    model: Optional[str] = None          # pin every *_model to this value
    keep_tmp: bool = False


@dataclass
class _State:
    messages: List[Dict[str, Any]] = field(default_factory=list)  # with observed_at, step
    last_change: float = 0.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _storage_ts(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ScenarioRunner:
    def __init__(self, case: Dict[str, Any], version: str, checkout: Path, out_dir: Path, opts: RunOptions):
        self.case = case
        self.version = version
        self.checkout = checkout
        self.out = out_dir
        self.opts = opts
        self.state = _State()
        self.tmp: Optional[Path] = None
        self.proc: Optional[subprocess.Popen] = None
        self.base_url = ""
        self.record = Path()

    # ------------------------------------------------------------------ lifecycle
    def run(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="openpoke-eval-"))
        try:
            self._prepare_copy()
            self._start_server()
            self._play()
        finally:
            self._stop_server()
            if self.record.exists():
                shutil.copy(self.record, self.out / "llm_calls.jsonl")
            if not self.opts.keep_tmp and self.tmp:
                shutil.rmtree(self.tmp, ignore_errors=True)

    def _prepare_copy(self) -> None:
        assert self.tmp is not None
        shutil.copytree(
            self.checkout / "server",
            self.tmp / "server",
            ignore=shutil.ignore_patterns("data", "__pycache__", "*.pyc"),
        )
        shutil.copy(self.opts.env_file, self.tmp / ".env")
        self.record = self.tmp / "llm_calls.jsonl"
        self.record.touch()

    def _overrides(self) -> Dict[str, Any]:
        overrides = {k: v for k, v in (self.case.get("config") or {}).items() if k != "timezone"}
        if self.opts.model:
            for key in ("interaction_agent_model", "execution_agent_model", "execution_agent_search_model",
                        "summarizer_model", "email_classifier_model"):
                overrides.setdefault(key, self.opts.model)
        return overrides

    def _start_server(self) -> None:
        assert self.tmp is not None
        port = _free_port()
        self.base_url = f"http://127.0.0.1:{port}/api/v1"
        log = open(self.out / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [self.opts.python, str(SERVE_SCRIPT), "--root", str(self.tmp), "--port", str(port),
             "--record", str(self.record), "--overrides", json.dumps(self._overrides())],
            stdout=log, stderr=subprocess.STDOUT, cwd=str(self.tmp),
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"server exited early; see {self.out / 'server.log'}")
            try:
                if httpx.get(f"{self.base_url}/meta", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise RuntimeError("server did not become ready within 60s")

    def _stop_server(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    # ------------------------------------------------------------------ playing
    def _play(self) -> None:
        tz_name = (self.case.get("config") or {}).get("timezone", self.opts.timezone)
        self._tz_name = tz_name
        httpx.post(f"{self.base_url}/meta/timezone", json={"timezone": tz_name}, timeout=10).raise_for_status()
        run_start = datetime.now(timezone.utc)
        (self.out / "meta.json").write_text(json.dumps({
            "case": self.case["id"], "group": self.case.get("group"), "version": self.version,
            "checkout": str(self.checkout), "timezone": tz_name, "run_start": run_start.isoformat(),
            "config": self.case.get("config") or {}, "model_override": self.opts.model,
        }, indent=2))

        steps: List[Dict[str, Any]] = []
        for index, step in enumerate(self.case["turns"], start=1):
            if "user" in step:
                entry = self._send(index, step["user"])
            elif "fire_triggers" in step:
                entry = self._fire(index, step["fire_triggers"])
            elif "wait_for_triggers" in step:
                entry = self._wait_for_triggers(index, step["wait_for_triggers"], step.get("timeout_s", WAIT_FIRE_TIMEOUT_SECONDS))
            else:
                raise ValueError(f"unknown step: {step}")
            steps.append(entry)
            self._snapshot(index)
            (self.out / "steps.json").write_text(json.dumps(steps, indent=2))

        (self.out / "transcript.json").write_text(json.dumps(self.state.messages, indent=2))

    def _render_text(self, text: str) -> str:
        """Fill `{in:Nm}` with the local clock time N minutes from now (rounded up), e.g. '1:23pm'."""
        tz = ZoneInfo(self._tz_name)

        def repl(match: "re.Match[str]") -> str:
            moment = datetime.now(tz) + timedelta(minutes=int(match.group(1)))
            moment = (moment + timedelta(minutes=1)).replace(second=0, microsecond=0)
            return moment.strftime("%I:%M%p").lstrip("0").lower()

        return re.sub(r"\{in:(\d+)m\}", repl, text)

    def _send(self, index: int, text: str) -> Dict[str, Any]:
        text = self._render_text(text)
        sent_at = time.time()
        response = httpx.post(
            f"{self.base_url}/chat/send",
            json={"messages": [{"role": "user", "content": text}]},
            timeout=30,
        )
        response.raise_for_status()
        done = self._wait_quiet(index, since=sent_at, timeout=TURN_TIMEOUT_SECONDS)
        return {"step": index, "kind": "user", "text": text, "started_at": sent_at, **done}

    def _fire(self, index: int, selector: str) -> Dict[str, Any]:
        assert self.tmp is not None
        db = self.tmp / "server" / "data" / "triggers.db"
        started = time.time()
        fired_ids: List[int] = []
        if db.exists():
            conn = sqlite3.connect(db, timeout=30)
            try:
                rows = conn.execute("SELECT id, payload FROM triggers WHERE status = 'active'").fetchall()
                pattern = None if str(selector).strip().lower() == "all" else re.compile(str(selector), re.I)
                fired_ids = [rid for rid, payload in rows if pattern is None or pattern.search(payload or "")]
                due = _storage_ts(datetime.now(timezone.utc) - timedelta(seconds=1))
                for rid in fired_ids:
                    conn.execute("UPDATE triggers SET next_trigger = ? WHERE id = ?", (due, rid))
                conn.commit()
            finally:
                conn.close()
        done = {"done_at": time.time(), "last_activity": time.time(), "timed_out": False, "llm_calls_seen": 0}
        if fired_ids:
            done = self._wait_quiet(index, since=started, timeout=FIRE_TIMEOUT_SECONDS)
        return {"step": index, "kind": "fire", "selector": selector, "fired_ids": fired_ids,
                "started_at": started, **done}

    def _wait_for_triggers(self, index: int, selector: str, timeout: float) -> Dict[str, Any]:
        """Wait (real time) until the matching active triggers have fired on their own schedule."""
        assert self.tmp is not None
        db = self.tmp / "server" / "data" / "triggers.db"
        started = time.time()
        pattern = None if str(selector).strip().lower() == "all" else re.compile(str(selector), re.I)

        def rows() -> Dict[int, tuple]:
            if not db.exists():
                return {}
            conn = sqlite3.connect(db, timeout=30)
            try:
                found = conn.execute("SELECT id, payload, status, next_trigger FROM triggers").fetchall()
            finally:
                conn.close()
            return {rid: (status, nxt) for rid, payload, status, nxt in found
                    if pattern is None or pattern.search(payload or "")}

        pending = {rid: v for rid, v in rows().items() if v[0] == "active"}
        fired: List[int] = []
        while pending and time.time() < started + timeout:
            self._poll_history(index)
            current = rows()
            for rid, (status, nxt) in list(pending.items()):
                now_status, now_next = current.get(rid, ("missing", None))
                if now_status != "active" or now_next != nxt:
                    fired.append(rid)
                    pending.pop(rid)
            time.sleep(1.0)
        done = self._wait_quiet(index, since=started, timeout=FIRE_TIMEOUT_SECONDS, clock_from=time.time()) if fired else {
            "done_at": time.time(), "last_activity": time.time(), "timed_out": False, "llm_calls_seen": 0}
        if pending:
            done["timed_out"] = True
        return {"step": index, "kind": "fire", "selector": selector, "fired_ids": fired,
                "not_fired_ids": list(pending), "started_at": started, **done}

    # ------------------------------------------------------------------ waiting
    def _poll_history(self, step: int) -> None:
        try:
            data = httpx.get(f"{self.base_url}/chat/history", timeout=10).json()
        except (httpx.HTTPError, ValueError):
            return
        messages = data.get("messages") or []
        known = len(self.state.messages)
        if len(messages) > known:
            now = time.time()
            for message in messages[known:]:
                self.state.messages.append({**message, "observed_at": now, "step": step})
            self.state.last_change = now

    def _llm_activity(self, since: float) -> tuple[int, int, float]:
        """Return (calls started since `since`, calls in flight, time of the last event)."""
        started, ended, recent, last = {}, set(), 0, 0.0
        for line in self.record.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue  # partially written line
            last = max(last, event.get("t", 0.0))
            if event.get("event") == "start":
                started[event["id"]] = event.get("t", 0.0)
                if event.get("t", 0.0) >= since:
                    recent += 1
            elif event.get("event") == "end":
                ended.add(event["id"])
        # A call open for over STUCK_CALL_SECONDS is treated as lost, so it can't stall turn detection.
        now = time.time()
        in_flight = sum(1 for cid, t in started.items() if cid not in ended and now - t < STUCK_CALL_SECONDS)
        return recent, in_flight, last

    def _wait_quiet(self, step: int, *, since: float, timeout: float, clock_from: Optional[float] = None) -> Dict[str, Any]:
        """Wait until an LLM call happened, none is in flight, and nothing changed for QUIET_SECONDS.

        LLM calls are counted from `since`; the timeout runs from `clock_from` (default: `since`).
        """
        deadline = (clock_from or since) + timeout
        self.state.last_change = max(self.state.last_change, since)
        while True:
            self._poll_history(step)
            recent, in_flight, last_llm = self._llm_activity(since)
            last_activity = max(self.state.last_change, last_llm, since)
            now = time.time()
            if recent > 0 and in_flight == 0 and now - last_activity >= QUIET_SECONDS:
                return {"done_at": now, "last_activity": last_activity, "timed_out": False, "llm_calls_seen": recent}
            if now > deadline:
                return {"done_at": now, "last_activity": last_activity, "timed_out": True, "llm_calls_seen": recent}
            time.sleep(POLL_SECONDS)

    # ------------------------------------------------------------------ snapshots
    def _snapshot(self, step: int) -> None:
        assert self.tmp is not None
        data = self.tmp / "server" / "data"
        target = self.out / "snapshots" / f"step_{step}"
        target.mkdir(parents=True, exist_ok=True)
        db = data / "triggers.db"
        if db.exists():
            src = sqlite3.connect(db, timeout=30)
            dst = sqlite3.connect(target / "triggers.db")
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        for rel in ("execution_agents/roster.json", "conversation/poke_working_memory.log",
                    "conversation/poke_conversation.log"):
            if (data / rel).exists():
                shutil.copy(data / rel, target / Path(rel).name)
        if (data / "execution_agents").exists():
            shutil.copytree(data / "execution_agents", target / "execution_agents", dirs_exist_ok=True)


def run_scenario(case: Dict[str, Any], version: str, checkout: Path, out_dir: Path, opts: RunOptions) -> Path:
    ScenarioRunner(case, version, checkout, out_dir, opts).run()
    return out_dir


__all__ = ["RunOptions", "run_scenario", "ScenarioRunner"]
