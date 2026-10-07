"""Black-box + white-box experiments against an unmodified OpenPoke server.

Usage:  ../../.venv-lab/bin/python run_experiments.py [scenario ...]
Scenarios: core race_exec summary_faithful summary_lossy summary_fail race_summary
Outputs: results/<scenario>.json and results/summary.md
All secrets / PII below are synthetic markers.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

LAB = Path(__file__).resolve().parent
REPO = LAB.parent.parent
DATA = REPO / "server" / "data"
STATE = LAB / "state"
RESULTS = LAB / "results"
PY = sys.executable
API = "http://127.0.0.1:18001/api/v1"
MOCK = "http://127.0.0.1:18080"

MARKERS = {
    "locker_code": "LOCKER-7781-SYNTH",
    "pii_email": "jane.synthetic@example.test",
    "api_key": "sk-test-SYNTHETIC-1234567890abcdef",
    "ssn_like": "000-12-3456",
    "card_test_number": "4111 1111 1111 1111",
    "otp_search_email": "482913",
    "otp_watched_email": "771204",
    "street_address": "42 Synthetic Lane",
    "trigger_pin": "GATE-PIN-5521",
    "openrouter_key": "sk-or-v1-SYNTHETIC-LAB-KEY-0000",
}

_procs: dict[str, subprocess.Popen] = {}


# ----------------------------------------------------------------------------- stack control
def _wait_http(url: str, timeout: float = 20) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            httpx.get(url, timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"{url} did not come up")


def start_mock() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    _procs["mock"] = subprocess.Popen([PY, str(LAB / "mock_openrouter.py"), "18080", str(STATE)],
                                      stdout=open(STATE / "mock.out", "a"), stderr=subprocess.STDOUT)
    _wait_http(MOCK + "/")


def start_server(env: dict | None = None) -> None:
    full_env = {**os.environ, "LAB_STATE": str(STATE), **(env or {})}
    _procs["server"] = subprocess.Popen([PY, str(LAB / "launch_server.py")], env=full_env,
                                        stdout=open(STATE / "server_stdout.log", "a"),
                                        stderr=subprocess.STDOUT)
    _wait_http(API + "/health")


def stop(name: str) -> None:
    proc = _procs.pop(name, None)
    if proc:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def fresh_stack(env: dict | None = None, inbox: list | None = None) -> None:
    stop("server"); stop("mock")
    shutil.rmtree(DATA, ignore_errors=True)
    shutil.rmtree(STATE, ignore_errors=True)
    STATE.mkdir(parents=True)
    (STATE / "inbox.json").write_text(json.dumps(inbox or []))
    start_mock(); start_server(env)


def control(**kwargs) -> None:
    httpx.post(MOCK + "/__control", json=kwargs)


# ----------------------------------------------------------------------------- observation
def captures() -> list[dict]:
    path = STATE / "llm_captures.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def composio_calls() -> list[dict]:
    path = STATE / "composio_calls.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def _fingerprint() -> tuple:
    files = sorted(DATA.rglob("*")) if DATA.exists() else []
    return (len(captures()), tuple((str(f), f.stat().st_mtime_ns) for f in files if f.is_file()))


def wait_idle(quiet: float = 2.0, timeout: float = 120) -> None:
    end = time.time() + timeout
    last, since = _fingerprint(), time.time()
    while time.time() < end:
        time.sleep(0.25)
        cur = _fingerprint()
        if cur != last:
            last, since = cur, time.time()
        elif time.time() - since >= quiet:
            return
    raise TimeoutError("system did not go idle")


def history() -> list[dict]:
    return httpx.get(API + "/chat/history", timeout=10).json()["messages"]


def send(text: str, quiet: float = 0.6) -> None:
    before = len(captures())
    r = httpx.post(API + "/chat/send", json={"messages": [{"role": "user", "content": text}]}, timeout=10)
    assert r.status_code == 202, r.text
    end = time.time() + 30
    while len(captures()) == before and time.time() < end:
        time.sleep(0.05)
    wait_idle(quiet=quiet)


def last_interaction_payload(after: int = 0) -> dict:
    caps = [c for c in captures()[after:] if c["category"] == "interaction_agent"]
    return caps[-1]["body"] if caps else {}


def user_content(body: dict) -> str:
    return next((m["content"] for m in body.get("messages", []) if m["role"] == "user"), "")


def section(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    return m.group(1) if m else ""


def scan_locations(markers: dict) -> dict:
    """Where does each marker physically exist right now?"""
    locs: dict[str, list[str]] = {k: [] for k in markers}
    files = [f for f in DATA.rglob("*") if f.is_file()] if DATA.exists() else []
    files += [STATE / "server_stdout.log"]
    for f in files:
        if not f.exists():
            continue
        blob = f.read_bytes()
        for key, val in markers.items():
            if val.encode() in blob:
                locs[key].append(str(f.relative_to(REPO) if f.is_relative_to(REPO) else f))
    for cap in captures():
        blob = json.dumps(cap["body"])
        for key, val in markers.items():
            tag = f"LLM:{cap['category']}"
            if val in blob and tag not in locs[key]:
                locs[key].append(tag)
    for call in composio_calls():
        blob = json.dumps(call)
        for key, val in markers.items():
            if val in blob and "COMPOSIO:" + call.get("tool", call["op"]) not in locs[key]:
                locs[key].append("COMPOSIO:" + call.get("tool", call["op"]))
    return locs


def data_files() -> dict:
    return {str(f.relative_to(REPO)): f.stat().st_size for f in sorted(DATA.rglob("*")) if f.is_file()} if DATA.exists() else {}


def now_iso(offset_s: int = 0) -> str:
    return datetime.fromtimestamp(time.time() + offset_s, timezone.utc).isoformat().replace("+00:00", "Z")


# ----------------------------------------------------------------------------- scenarios
def scenario_core() -> dict:
    out: dict = {}
    inbox = [{
        "id": "msg-search-1", "subject": "Your Synthetic Bank verification code",
        "sender": "Synthetic Bank <alerts@bank.example.test>", "to": "lab-user-A@example.test",
        "ts": now_iso(-3600), "attachments": ["statement_SYNTH.pdf"],
        "body": f"Your verification code is {MARKERS['otp_search_email']}. Card on file ships to "
                f"{MARKERS['street_address']}, Springfield. Do not share this code.",
    }]
    fresh_stack(inbox=inbox)
    httpx.post(API + "/meta/timezone", json={"timezone": "America/New_York"})
    httpx.post(API + "/gmail/connect", json={"user_id": "lab-user-A"})
    st = httpx.post(API + "/gmail/status", json={"user_id": "lab-user-A"}).json()
    out["gmail_status_response_keys"] = sorted(st)
    time.sleep(4)  # watcher warm-up poll marks existing inbox as seen

    # --- facts across turns
    send(f"My locker code is {MARKERS['locker_code']} and my backup email is {MARKERS['pii_email']}.")
    send(f"My test API key is {MARKERS['api_key']}, my fake SSN is {MARKERS['ssn_like']}, "
         f"card {MARKERS['card_test_number']}.")
    n = len(captures())
    send("What's my locker code?")
    body = last_interaction_payload(n)
    hist = section(user_content(body), "conversation_history")
    out["turn_persistence"] = {
        "locker_code_in_next_turn_history": MARKERS["locker_code"] in hist,
        "api_key_in_next_turn_history": MARKERS["api_key"] in hist,
        "history_source": "working_memory_log.render_transcript (raw tail, no summary yet)",
        "interaction_payload_message_count": len(body["messages"]),
        "system_prompt_chars": len(body["messages"][0]["content"]),
        "tools_sent": [t["function"]["name"] for t in body.get("tools", [])],
    }

    # --- execution agent + gmail search
    n = len(captures())
    send("DELEGATE: search my email for the bank verification code", quiet=2.5)
    caps = captures()[n:]
    out["delegation_call_sequence"] = [c["category"] for c in caps]
    exec_first = next(c for c in caps if c["category"] == "execution_agent")["body"]
    out["execution_agent_input"] = {
        "system_prompt_contains_execution_history": "# Execution History" in exec_first["messages"][0]["content"],
        "receives_interaction_conversation_history": "<conversation_history>" in json.dumps(exec_first),
        "user_message": exec_first["messages"][1]["content"],
    }
    search_tool_msgs = [m for c in caps if c["category"] == "search_subagent"
                        for m in c["body"]["messages"] if m["role"] == "tool"]
    raw = search_tool_msgs[0]["content"] if search_tool_msgs else ""
    out["search_tool_result_wire_format"] = "python_repr_fallback" if raw.startswith('{"repr"') else "json"
    first_msg = raw.split("'messages': [{", 1)[-1].split("}, {", 1)[0]
    out["gmail_fields_to_search_subagent_llm"] = sorted(set(re.findall(r"'(\w+)': ", first_msg)))
    exec_tool_msgs = [m for c in caps if c["category"] == "execution_agent"
                      for m in c["body"]["messages"] if m["role"] == "tool"]
    exec_result = json.loads(exec_tool_msgs[0]["content"]) if exec_tool_msgs else {}
    out["gmail_fields_to_execution_agent_llm"] = sorted((exec_result.get("result") or [{}])[0])
    out["otp_body_reached_interaction_agent"] = any(
        MARKERS["otp_search_email"] in json.dumps(c["body"]) for c in caps if c["category"] == "interaction_agent")

    # --- trigger persistence (scheduler fires immediately because start_time defaults to now)
    send(f"DELEGATE: TRIGGER: remind me daily that my gate PIN is {MARKERS['trigger_pin']}", quiet=3)
    con = sqlite3.connect(DATA / "triggers.db")
    out["trigger_rows"] = [dict(zip([d[0] for d in con.execute("select * from triggers").description], r))
                           for r in con.execute("select * from triggers")]
    con.close()

    # --- watcher classifier path
    inbox.append({
        "id": "msg-watch-2", "subject": "Your sign-in code", "sender": "Synthetic Login <no-reply@login.example.test>",
        "to": "lab-user-A@example.test", "ts": now_iso(), "attachments": [],
        "body": f"Use code {MARKERS['otp_watched_email']} to sign in. Request came from {MARKERS['street_address']}.",
    })
    (STATE / "inbox.json").write_text(json.dumps(inbox))
    n = len(captures())
    end = time.time() + 20
    while not any(c["category"] == "email_classifier" for c in captures()[n:]) and time.time() < end:
        time.sleep(0.3)
    wait_idle(quiet=2.5)
    clf = next((c for c in captures()[n:] if c["category"] == "email_classifier"), None)
    out["email_classifier_payload"] = clf["body"]["messages"][-1]["content"] if clf else None
    out["watcher_summary_in_conversation_log"] = MARKERS["otp_watched_email"] in (
        DATA / "conversation" / "poke_conversation.log").read_text()

    out["locations_before_restart"] = scan_locations(MARKERS)
    out["data_files_before_restart"] = data_files()

    # --- restart
    hist_before = history()
    stop("server")
    fetches_before = sum(1 for c in composio_calls() if c.get("tool") == "GMAIL_FETCH_EMAILS")
    start_server()
    time.sleep(7)
    fetches_after = sum(1 for c in composio_calls() if c.get("tool") == "GMAIL_FETCH_EMAILS")
    n = len(captures())
    send("What's my locker code?")
    body = last_interaction_payload(n)
    out["restart"] = {
        "history_len_before": len(hist_before), "history_len_after": len(history()) - 2,
        "locker_code_in_llm_history_after_restart": MARKERS["locker_code"] in user_content(body),
        "roster_after_restart": json.loads((DATA / "execution_agents" / "roster.json").read_text()),
        "watcher_gmail_fetches_in_7s_after_restart": fetches_after - fetches_before,
        "note": "active Gmail user id is in-process memory only; watcher idles until a client re-POSTs /gmail/status",
    }

    # --- scoping
    other = httpx.get(API + "/chat/history", headers={"X-User": "someone-else"}).json()["messages"]
    httpx.post(API + "/gmail/status", json={"user_id": "lab-user-B"})
    n_calls = len(composio_calls())
    send("DELEGATE: search my email for anything from the bank", quiet=2.5)
    used_ids = sorted({c.get("user_id") for c in composio_calls()[n_calls:] if c["op"] == "tools.execute"})
    out["scoping"] = {
        "unauthenticated_other_client_sees_locker_code": MARKERS["locker_code"] in json.dumps(other),
        "composio_user_ids_used_after_user_B_status_call": used_ids,
        "execution_agent_log_files": sorted(p.name for p in (DATA / "execution_agents").iterdir()),
        "all_paths_user_scoped": False,
    }

    # --- deletion
    r = httpx.delete(API + "/chat/history")
    time.sleep(1)
    out["delete_status"] = r.status_code
    out["locations_after_delete"] = scan_locations(MARKERS)
    out["data_files_after_delete"] = data_files()
    stop("server")
    return out


def scenario_race_exec() -> dict:
    marker = {"race": "RACE-MARKER-9090"}
    fresh_stack()
    control(delay={"execution_agent": 4})
    httpx.post(API + "/chat/send", json={"messages": [{"role": "user", "content": f"DELEGATE: note {marker['race']}"}]})
    time.sleep(2.0)  # interaction turn done, execution agent still in flight
    in_flight = scan_locations(marker)
    httpx.delete(API + "/chat/history")
    right_after = scan_locations(marker)
    wait_idle(quiet=3)
    res = {
        "locations_before_delete": in_flight,
        "locations_immediately_after_delete": right_after,
        "locations_after_inflight_work_finished": scan_locations(marker),
        "history_after": history(),
        "data_files_after": data_files(),
    }
    stop("server")
    return res


def _summary_run(mode: str, env: dict | None = None, turns: int = 56) -> dict:
    fresh_stack(env=env)
    control(summarizer_mode=mode)
    script = {0: "My dentist is Dr. Alpha Synthetic.", 1: "My locker code is LOCKER-OLD-1111.",
              48: "Correction: my dentist is now Dr. Beta Synthetic.", 49: "My locker code changed to LOCKER-NEW-2222."}
    first_summary_at = None
    for i in range(turns):
        send(script.get(i, f"Filler message number {i}."), quiet=0.4)
        if first_summary_at is None and any(c["category"] == "summarizer" for c in captures()):
            first_summary_at = {"turn": i, "conversation_entries": 2 * (i + 1)}
    wait_idle(quiet=2)
    summ = [c for c in captures() if c["category"] == "summarizer"]
    summ_input = user_content(summ[0]["body"]) if summ else ""
    n = len(captures())
    send("What is my dentist and locker code?")
    probe = user_content(last_interaction_payload(n))
    hist = section(probe, "conversation_history")
    wm = (DATA / "conversation" / "poke_working_memory.log").read_text()
    conv = (DATA / "conversation" / "poke_conversation.log").read_text()
    facts = ["Dr. Alpha Synthetic", "Dr. Beta Synthetic", "LOCKER-OLD-1111", "LOCKER-NEW-2222"]
    res = {
        "summarizer_mode": mode,
        "env": env or {},
        "first_summarizer_call": first_summary_at,
        "summarizer_calls": len(summ),
        "summarizer_input_entry_indices": [int(x) for x in re.findall(r"^\s*\[(\d+)\]", summ_input, re.M)][:1]
                                          + [int(x) for x in re.findall(r"^\s*\[(\d+)\]", summ_input, re.M)][-1:],
        "summarizer_input_entry_count": len(re.findall(r"^\s*\[\d+\]", summ_input, re.M)),
        "summarizer_input_head": summ_input[:260],
        "summarizer_input_tags": sorted(set(re.findall(r"^\s*\[\d+\] ([a-z ]+):", summ_input, re.M))),
        "probe_history_has_summary_block": "<conversation_summary>" in hist,
        "probe_history_raw_entries": len(re.findall(r"<(user_message|poke_reply|agent_message|wait) ", hist)),
        "fact_visible_to_llm_on_probe": {f: f in hist for f in facts},
        "fact_in_working_memory_file": {f: f in wm for f in facts},
        "fact_in_conversation_log_file": {f: f in conv for f in facts},
        "fact_in_history_api": {f: f in json.dumps(history()) for f in facts},
        "conversation_log_lines": len(conv.splitlines()),
        "working_memory_summary_info": wm.splitlines()[0] if wm else None,
        "working_memory_lines": len(wm.splitlines()),
        "summary_block_in_working_memory": next((l[:400] for l in wm.splitlines() if l.startswith("<conversation_summary")), None),
    }
    if summ:
        res["summarizer_payload_chars"] = [len(json.dumps(c["body"])) for c in summ]
    stop("server")
    return res


def scenario_summary_faithful() -> dict:
    return _summary_run("faithful")


def scenario_summary_lossy() -> dict:
    return _summary_run("lossy")


def scenario_summary_fail() -> dict:
    # Lower thresholds (process-local override) so the failure loop shows up quickly.
    return _summary_run("fail", env={"LAB_SUMMARY_THRESHOLD": "10", "LAB_SUMMARY_TAIL": "2"}, turns=12)


def scenario_race_summary() -> dict:
    marker = "SUMMARY-RACE-SECRET-3141"
    fresh_stack(env={"LAB_SUMMARY_THRESHOLD": "10", "LAB_SUMMARY_TAIL": "2"})
    control(summarizer_mode="faithful", delay={"summarizer": 4})
    send(f"My vault phrase is {marker}.", quiet=0.3)
    for i in range(10):
        send(f"Filler {i}", quiet=0.2)
        if any(c["category"] == "summarizer" for c in captures()):
            break
    t_summary_started = any(c["category"] == "summarizer" for c in captures())
    httpx.delete(API + "/chat/history")
    after_delete = scan_locations({"m": marker})["m"]
    time.sleep(6)  # let the in-flight summariser finish and write its state
    wm = (DATA / "conversation" / "poke_working_memory.log").read_text()
    control(delay={})
    n = len(captures())
    send("Hello again after deleting everything.")
    probe = user_content(last_interaction_payload(n))
    res = {
        "summarizer_in_flight_at_delete": t_summary_started,
        "marker_locations_immediately_after_delete": after_delete,
        "working_memory_after_summarizer_finished_first_line": wm.splitlines()[0],
        "marker_in_working_memory_after_delete": marker in wm,
        "marker_sent_to_llm_on_next_turn_after_delete": marker in probe,
        "conversation_log_after_delete_lines": len((DATA / "conversation" / "poke_conversation.log").read_text().splitlines()),
    }
    stop("server")
    return res


SCENARIOS = {
    "core": scenario_core,
    "race_exec": scenario_race_exec,
    "summary_faithful": scenario_summary_faithful,
    "summary_lossy": scenario_summary_lossy,
    "summary_fail": scenario_summary_fail,
    "race_summary": scenario_race_summary,
}


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    names = sys.argv[1:] or list(SCENARIOS)
    try:
        for name in names:
            t0 = time.time()
            print(f"== {name}", flush=True)
            result = SCENARIOS[name]()
            result["_elapsed_s"] = round(time.time() - t0, 1)
            (RESULTS / f"{name}.json").write_text(json.dumps(result, indent=2, default=str))
            shutil.copy(STATE / "llm_captures.jsonl", RESULTS / f"{name}.llm_captures.jsonl") \
                if (STATE / "llm_captures.jsonl").exists() else None
            print(f"   done in {result['_elapsed_s']}s", flush=True)
    finally:
        stop("server"); stop("mock")


if __name__ == "__main__":
    main()
