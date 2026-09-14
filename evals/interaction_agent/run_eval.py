"""Run interaction-agent eval cases against the real model and score them.

Usage (from repo root, with OPENROUTER_API_KEY in .env or the environment):

    .venv/bin/python evals/interaction_agent/run_eval.py --case IA-01
    .venv/bin/python evals/interaction_agent/run_eval.py --type follow_up
    .venv/bin/python evals/interaction_agent/run_eval.py            # all cases
    .venv/bin/python evals/interaction_agent/run_eval.py --model config   # use the server's configured model

Runs default to a cheap model (anthropic/claude-haiku-4.5) for the agent under test and to the
server's configured model (a stronger one) for the judge, so grading quality does not depend on
the model being graded.

What it does per run:
  1. Points every file-backed store (conversation log, working memory, roster,
     execution-agent logs) at a fresh temp directory.
  2. Seeds history and roster from the case, expanding filler / generated
     entries, then runs the summarizer to steady state so compaction reflects
     what a long-lived conversation would look like.
  3. Replaces the execution batch manager with a fake that records dispatches
     and never runs a worker, so only the interaction agent is under test.
  4. Wraps the OpenRouter call to capture every prompt/response, token usage
     and timing.
  5. Runs one interaction-agent turn on the probe, scores it against the
     case's assert block, and writes results + full traces to a results dir.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import random
import sys
import tempfile
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CASES_PATH = HERE / "cases.json"
RESULTS_ROOT = HERE / "results"

# ---------------------------------------------------------------------------
# Server imports (after sys.path fix)
# ---------------------------------------------------------------------------
from server.config import get_settings  # noqa: E402
from server.logging_config import configure_logging, logger  # noqa: E402
from server.services.conversation import get_conversation_log  # noqa: E402
from server.services.conversation.summarization import get_working_memory_log  # noqa: E402
from server.services.conversation.summarization.summarizer import summarize_conversation  # noqa: E402
from server.services.execution import get_agent_roster, get_execution_agent_logs  # noqa: E402
import server.agents.interaction_agent.runtime as ia_runtime  # noqa: E402
import server.agents.interaction_agent.tools as ia_tools  # noqa: E402
import server.services.conversation.summarization.summarizer as summarizer_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Filler / generators
# ---------------------------------------------------------------------------
_FILLER_PAIRS = [
    ("how's the weather looking today", "mostly sunny, high of 72"),
    ("any good lunch spots near the office", "the taco place on 3rd is solid"),
    ("what's a good name for a golden retriever", "biscuit. no contest"),
    ("did the giants win last night", "yep, 4-2"),
    ("how many ounces in a cup", "8"),
    ("recommend a podcast for the drive", "try Acquired, the episodes are long but great"),
    ("is it friday yet", "not even close"),
    ("what time zone is lisbon", "WEST, same as london right now"),
    ("what's the capital of australia", "canberra, not sydney"),
    ("coffee or tea this morning", "coffee. always coffee"),
    ("how long to boil an egg", "7 minutes for jammy, 10 for hard"),
    ("thanks", "anytime"),
]

_FIRST_NAMES = ["Alex", "Priya", "Chen", "Maria", "Omar", "Lena", "Diego", "Aisha", "Tom", "Yuki",
                "Noah", "Fatima", "Ivan", "Grace", "Raj", "Elena", "Kofi", "Sofia", "Liam", "Zara"]
_TOPICS = ["Dentist", "Gym", "Invoice", "Lease", "Insurance", "Passport", "Car Service", "Vet",
           "Standup", "Budget", "Taxes", "Conference", "Birthday", "Rent", "Payroll", "Onboarding"]


_PAD_SENTENCES = [
    "Also, while I remember, the quarterly planning doc still needs the headcount section filled in before Thursday.",
    "The contractor said the kitchen tiles are backordered until the 22nd, so the install slips a week.",
    "I read a piece about how container ports are automating crane scheduling; the throughput gains were bigger than I expected.",
    "My sister is visiting the second weekend of next month and wants to do the coastal hike if the weather holds.",
    "The car's brake pads are at about 30 percent, so that service is due within the next couple thousand miles.",
    "For the offsite, the venue wants a final headcount ten days out and a deposit of half the room fee.",
    "The neighbor's dog got out again yesterday; the fence latch on the alley side keeps sticking.",
    "I switched the home router to the 5 GHz band for the office and the video calls stopped dropping.",
]


def _pad(text: str, approx_tokens: int, seed: int) -> str:
    """Extend a short message with plausible rambling until it reaches ~approx_tokens (4 chars/token)."""
    if approx_tokens <= 0:
        return text
    rng = random.Random(seed)
    target = approx_tokens * 4
    parts = [text]
    size = len(text)
    while size < target:
        sentence = rng.choice(_PAD_SENTENCES)
        parts.append(sentence)
        size += len(sentence) + 1
    return " ".join(parts)


def make_filler(count: int, entry_tokens: int = 0) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    i = 0
    while len(out) < count:
        u, r = _FILLER_PAIRS[i % len(_FILLER_PAIRS)]
        out.append({"role": "user", "content": _pad(u, entry_tokens, i * 2)})
        if len(out) < count:
            out.append({"role": "reply", "content": _pad(r, entry_tokens, i * 2 + 1)})
        i += 1
    return out


def make_roster_names(count: int, pattern: str, seed: int = 7) -> List[str]:
    rng = random.Random(seed)
    templates = pattern.split("|")
    names: List[str] = []
    seen = set()
    attempts = 0
    while len(names) < count:
        t = rng.choice(templates)
        name = t.replace("{first_name}", rng.choice(_FIRST_NAMES)).replace("{topic}", rng.choice(_TOPICS))
        attempts += 1
        if name in seen:
            if attempts > count * 20:  # template space exhausted: disambiguate with a suffix
                name = f"{name} {len(names) + 1}"
            else:
                continue
        seen.add(name)
        names.append(name)
    return names


def make_email_thread(approx_tokens: int, seed: int = 11) -> str:
    rng = random.Random(seed)
    people = ["vendor-support@northwind.example", "alex@acme.com", "billing@northwind.example"]
    subjects = ["Re: PO-4471 delivery window", "Re: Re: PO-4471 delivery window", "Fwd: revised quote"]
    lines: List[str] = []
    approx_chars = approx_tokens * 4
    n = 0
    while sum(len(l) + 1 for l in lines) < approx_chars:
        n += 1
        lines.append(f"---- Message {n} ----")
        lines.append(f"From: {rng.choice(people)}")
        lines.append(f"To: {rng.choice(people)}")
        lines.append(f"Subject: {rng.choice(subjects)}")
        lines.append("")
        for _ in range(rng.randint(3, 7)):
            lines.append(
                "Following up on the revised delivery window for PO-4471. Our warehouse confirmed the pallets "
                "can ship on the " + str(rng.randint(1, 28)) + "th, pending the updated quote of $"
                + str(rng.randint(1200, 9800)) + ". Please confirm the dock hours and whether the liftgate is required."
            )
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Case expansion
# ---------------------------------------------------------------------------
@dataclass
class Run:
    case: Dict[str, Any]
    run_id: str
    sweep_param: Optional[str] = None
    sweep_value: Optional[Any] = None
    history: List[Dict[str, str]] = field(default_factory=list)
    roster: List[str] = field(default_factory=list)


def expand_case(case: Dict[str, Any], sweep_override: Optional[List[int]] = None) -> List[Run]:
    sweep = case.get("sweep")
    values: List[Any] = [None]
    param = None
    if sweep:
        param = sweep["param"]
        values = sweep_override or sweep["values"]

    runs: List[Run] = []
    for v in values:
        history: List[Dict[str, str]] = []
        for h in case.get("history", []):
            if h.get("filler"):
                spec = h["filler"] if isinstance(h["filler"], dict) else {}
                count = int(spec.get("count", case.get("filler_count", 0)))
                entry_tokens = int(spec.get("entry_tokens", 0))
                if param == "filler_count":
                    count = int(v)
                elif param == "filler_entry_tokens":
                    entry_tokens = int(v)
                history.extend(make_filler(count, entry_tokens))
                continue
            entry = {"role": h["role"], "content": h["content"]}
            gen = h.get("generate")
            if gen and gen.get("kind") == "email_thread":
                entry["content"] = h["content"] + "\n\n" + make_email_thread(int(gen.get("approx_tokens", 4000)))
            history.append(entry)

        roster = list(case.get("roster", []))
        rg = case.get("roster_generate")
        if rg:
            decoys = make_roster_names(int(rg["count"]), rg["pattern"])
            # keep the real one somewhere in the middle so position is not a giveaway
            mid = len(decoys) // 2
            roster = decoys[:mid] + roster + decoys[mid:]

        run_id = case["id"] if v is None else f"{case['id']}@{param}={v}"
        runs.append(Run(case=case, run_id=run_id, sweep_param=param, sweep_value=v, history=history, roster=roster))
    return runs


# ---------------------------------------------------------------------------
# Store redirection
# ---------------------------------------------------------------------------
def redirect_stores(data_dir: Path) -> None:
    conv = get_conversation_log()
    wm = get_working_memory_log()
    roster = get_agent_roster()
    exec_logs = get_execution_agent_logs()

    conv._path = data_dir / "conversation" / "poke_conversation.log"
    conv._ensure_directory()
    wm._path = data_dir / "conversation" / "poke_working_memory.log"
    wm._ensure_directory()
    wm.clear()
    roster._roster_path = data_dir / "execution_agents" / "roster.json"
    roster._roster_path.parent.mkdir(parents=True, exist_ok=True)
    roster._agents = []
    roster.save()
    exec_logs._base_dir = data_dir / "execution_agents"
    exec_logs._base_dir.mkdir(parents=True, exist_ok=True)


def seed(run: Run) -> None:
    conv = get_conversation_log()
    for h in run.history:
        if h["role"] == "user":
            conv.record_user_message(h["content"])
        elif h["role"] == "reply":
            conv.record_reply(h["content"])
        elif h["role"] == "agent":
            conv.record_agent_message(h["content"])
        else:
            raise ValueError(f"unknown history role {h['role']!r} in {run.run_id}")
    roster = get_agent_roster()
    for name in run.roster:
        roster.add_agent(name)


# ---------------------------------------------------------------------------
# Instrumentation
# ---------------------------------------------------------------------------
def estimate_tokens(system: Optional[str], messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> int:
    """Cheap upper-ish bound: ~4 chars per token over everything we would send."""
    chars = len(system or "")
    for m in messages:
        c = m.get("content")
        chars += len(c) if isinstance(c, str) else len(json.dumps(c, ensure_ascii=False))
        if m.get("tool_calls"):
            chars += len(json.dumps(m["tool_calls"], ensure_ascii=False))
    if tools:
        chars += len(json.dumps(tools, ensure_ascii=False))
    return chars // 4


class HarnessTokenGate(Exception):
    """Raised instead of calling OpenRouter when a prompt exceeds the configured limit."""


class RateLimiter:
    """Sliding-window pacing so the suite never exceeds a provider RPM cap, plus 429 backoff."""

    def __init__(self, max_per_minute: int) -> None:
        self.max_per_minute = max_per_minute
        self._stamps: List[float] = []

    async def acquire(self) -> None:
        if self.max_per_minute <= 0:
            return
        while True:
            now = time.monotonic()
            self._stamps = [t for t in self._stamps if now - t < 60.0]
            if len(self._stamps) < self.max_per_minute:
                self._stamps.append(now)
                return
            await asyncio.sleep(max(0.2, 60.0 - (now - self._stamps[0]) + 0.1))


RATE_LIMITER = RateLimiter(max_per_minute=18)
MAX_429_RETRIES = 6


class Tracer:
    def __init__(self, max_input_tokens: int) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.phase = "seed"
        self.max_input_tokens = max_input_tokens

    def wrap(self, real, phase_label: str):
        async def _traced(*, model, messages, system=None, api_key=None, tools=None, **kw):
            snapshot = copy.deepcopy(messages)  # runtime mutates this list across rounds
            t0 = time.perf_counter()
            error = None
            response: Dict[str, Any] = {}
            try:
                est = estimate_tokens(system, messages, tools)
                if est > self.max_input_tokens:
                    # Emulate the provider's context-length rejection locally so the request is never billed.
                    raise HarnessTokenGate(
                        f"harness token gate: estimated {est:,} input tokens exceeds limit {self.max_input_tokens:,}; "
                        f"request blocked before reaching OpenRouter"
                    )
                for attempt in range(MAX_429_RETRIES + 1):
                    await RATE_LIMITER.acquire()
                    try:
                        response = await real(model=model, messages=messages, system=system, api_key=api_key, tools=tools, **kw)
                        break
                    except Exception as exc:
                        if "429" in str(exc) and attempt < MAX_429_RETRIES:
                            delay = min(60.0, 5.0 * (2 ** attempt))
                            logger.warning(f"429 from provider; retrying in {delay:.0f}s (attempt {attempt + 1})")
                            await asyncio.sleep(delay)
                            continue
                        raise
                return response
            except Exception as exc:  # re-raise after recording
                error = repr(exc)
                raise
            finally:
                usage = response.get("usage") or {}
                self.calls.append({
                    "phase": self.phase,
                    "component": phase_label,
                    "model": model,
                    "wall_ms": round((time.perf_counter() - t0) * 1000),
                    "system": system,
                    "messages": snapshot,
                    "tools": [t["function"]["name"] for t in (tools or [])],
                    "response": response,
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                    },
                    "estimated_input_tokens": estimate_tokens(system, snapshot, tools),
                    "error": error,
                })
        return _traced


class FakeBatchManager:
    """Records dispatches; never runs a worker, never calls back."""

    def __init__(self) -> None:
        self.dispatches: List[Dict[str, str]] = []

    async def execute_agent(self, agent_name: str, instructions: str, request_id: Optional[str] = None):
        self.dispatches.append({"agent_name": agent_name, "instructions": instructions})

        class _R:  # minimal ExecutionResult stand-in
            success = True
            response = "(stubbed)"
            error = None
        return _R()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def extract_tool_calls(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in calls:
        if c["phase"] != "probe" or c["component"] != "interaction_agent":
            continue
        choice = (c["response"].get("choices") or [{}])[0]
        for tc in (choice.get("message") or {}).get("tool_calls") or []:
            fn = tc.get("function") or {}
            args_raw = fn.get("arguments")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            except json.JSONDecodeError:
                args = {"__raw__": args_raw}
            out.append({"name": fn.get("name"), "arguments": args})
    return out


def _contains(hay: str, needle: str) -> bool:
    return needle.lower() in (hay or "").lower()


def score(run: Run, tool_calls: List[Dict[str, Any]], dispatches: List[Dict[str, str]]) -> Dict[str, Any]:
    a = run.case.get("assert", {})
    failures: List[str] = []
    names = [t["name"] for t in tool_calls]

    for t in a.get("must_call", []):
        if t not in names:
            failures.append(f"must_call: {t} not called (called: {names})")
    for t in a.get("must_not_call", []):
        if t in names:
            failures.append(f"must_not_call: {t} was called")

    replies = [t["arguments"].get("message", "") for t in tool_calls if t["name"] == "send_message_to_user"]
    if a.get("reply_contains_any"):
        if not any(_contains(r, n) for r in replies for n in a["reply_contains_any"]):
            failures.append(f"reply_contains_any: none of {a['reply_contains_any']} in replies {replies}")

    d = a.get("dispatch", {})
    n = len(dispatches)
    if "min_dispatches" in d and n < d["min_dispatches"]:
        failures.append(f"dispatch.min_dispatches: {n} < {d['min_dispatches']}")
    if "max_dispatches" in d and n > d["max_dispatches"]:
        failures.append(f"dispatch.max_dispatches: {n} > {d['max_dispatches']}")

    if n:
        chosen = [x["agent_name"] for x in dispatches]
        joined_instr = "\n".join(x["instructions"] for x in dispatches)
        if d.get("agent_name_in") and not any(c in d["agent_name_in"] for c in chosen):
            failures.append(f"dispatch.agent_name_in: chose {chosen}, expected one of {d['agent_name_in']}")
        if d.get("agent_name_new") is True and all(c in run.roster for c in chosen):
            failures.append(f"dispatch.agent_name_new: reused existing {chosen}, expected a new agent")
        for s in d.get("instructions_contains_all", []):
            if not _contains(joined_instr, s):
                failures.append(f"dispatch.instructions_contains_all: missing {s!r}")
        if d.get("instructions_contains_any") and not any(_contains(joined_instr, s) for s in d["instructions_contains_any"]):
            failures.append(f"dispatch.instructions_contains_any: none of {d['instructions_contains_any']}")
        for s in d.get("instructions_not_contains_all", []):
            if _contains(joined_instr, s):
                failures.append(f"dispatch.instructions_not_contains_all: found {s!r}")
    else:
        if d.get("agent_name_in") or d.get("instructions_contains_all") or d.get("instructions_contains_any"):
            if "send_message_to_agent" in a.get("must_call", []):
                failures.append("dispatch: no dispatch recorded")

    return {"pass": not failures, "failures": failures, "replies": replies}


def metrics_from(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    probe = [c for c in calls if c["phase"] == "probe" and c["component"] == "interaction_agent"]
    seedc = [c for c in calls if c["phase"] == "seed"]

    def tok(cs, key):
        vals = [c["usage"].get(key) for c in cs]
        return sum(v for v in vals if isinstance(v, int)) if any(isinstance(v, int) for v in vals) else None

    return {
        "llm_rounds": len(probe),
        "input_tokens": tok(probe, "prompt_tokens"),
        "output_tokens": tok(probe, "completion_tokens"),
        "llm_wall_ms": sum(c["wall_ms"] for c in probe),
        "seed_summarizer_calls": len(seedc),
        "seed_summarizer_tokens": tok(seedc, "prompt_tokens"),
    }



# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------
JUDGE_MODEL: Optional[str] = None  # set from CLI; falls back to the interaction-agent model

_JUDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "grade_run",
        "description": "Record the verdict for one evaluation run.",
        "parameters": {
            "type": "object",
            "properties": {
                "pass": {"type": "boolean", "description": "true if the agent's tool calls effectively lead to the task being done as the test case describes."},
                "rationale": {"type": "string", "description": "Two or three sentences citing the specific tool calls or omissions that decided the verdict."},
            },
            "required": ["pass", "rationale"],
            "additionalProperties": False,
        },
    },
}

_JUDGE_SYSTEM = """You are grading one turn of an orchestration agent called the interaction agent.

The interaction agent talks to a user and cannot do work itself. Its only tools are:
- send_message_to_user(message): show text to the user
- send_message_to_agent(agent_name, instructions): hand a task to a named background worker. Reusing an existing name gives the worker its prior context (thread IDs, drafts). A new name starts a worker with no memory.
- send_draft(to, subject, body): show an email draft to the user for review
- wait(reason): stay silent to avoid repeating something already said
- recall_history(entry_ids | query): fetch full text of earlier entries that were shown only as an index line or truncated preview (only available under the budgeted context strategy). Using it is a normal, correct step when details are not visible inline.

Workers run asynchronously; their results arrive in a later turn as an agent message. When the new message is an agent message, the turn under grading IS that later turn: the agent must relay the result to the user (send_draft for a draft, then send_message_to_user; or a short send_message_to_user for a notice) and must not re-dispatch work that is already done. Plain assistant text that is not a tool call is still delivered to the user as a reply by the runtime.

You are given the test case (what it tests and what a correct outcome looks like), the conversation context the agent saw, the new user message, and everything the agent did in this turn. Decide whether the agent's actions in THIS turn effectively lead to the task being done. Judge outcomes, not style: the acknowledgement wording, tool ordering, or a harmless wait call do not matter. What matters is whether the right worker was engaged with instructions that carry the information it needs, or the user was answered directly when no worker was needed, and nothing forbidden by the case happened.

Two hard facts about this system that decide many verdicts:
- The interaction agent cannot create or send email itself. send_draft only displays text to the user; it creates nothing. Only a worker (via send_message_to_agent) can create, send, reply to or forward an email. So when the task requires an email to be produced or sent, a turn that shows a draft or asks for details WITHOUT dispatching a worker has not advanced the task, no matter how good the draft text looks. Grade it fail.
- When the new message is a worker result (callback turn), relaying that result with send_draft / send_message_to_user IS the task; do not require a dispatch there.

Grade what the agent actually did against what the task needed. Ignore any prediction about how the current code is expected to behave; you are not checking whether a prediction came true. A turn in which the task was not advanced is a fail even if that was anticipated.

Call grade_run exactly once."""


def _judge_history_view(run: Run, max_entries: int = 24) -> str:
    h = run.history
    if len(h) <= max_entries:
        shown = h
        note = ""
    else:
        head, tail = h[:8], h[-(max_entries - 8):]
        shown = head + [{"role": "note", "content": f"... {len(h) - len(head) - len(tail)} routine chat entries omitted ..."}] + tail
        note = f" ({len(h)} entries total)"
    lines = [f"[{e['role']}] {e['content'][:600]}" for e in shown]
    return ("\n".join(lines) if lines else "(empty)") + note


async def judge_run(run: Run, tool_calls: List[Dict[str, Any]], dispatches: List[Dict[str, str]],
                    replies: List[str], exec_info: Dict[str, Any], checks: Dict[str, Any],
                    settings, real_llm) -> Dict[str, Any]:
    case = run.case
    actions = "\n".join(
        f"{i+1}. {t['name']}({json.dumps(t['arguments'], ensure_ascii=False)})" for i, t in enumerate(tool_calls)
    ) or "(no tool calls)"
    user_msg = f"""## Test case {case['id']} ({case['type']})
What this tests: {case['description']}
Expected result: {case['expected_result']}

## Roster before the turn (existing worker names)
{', '.join(run.roster) if run.roster else '(empty)'}{' — ' + str(len(run.roster)) + ' names' if len(run.roster) > 12 else ''}

## Conversation history the agent saw
{_judge_history_view(run)}

## New message ({'from a background worker or watcher, delivered via handle_agent_message; the user has NOT seen it' if case.get('probe_role') == 'agent' else 'from the user'})
{case['probe']}

## What the agent did this turn
Turn status: {'completed' if exec_info.get('turn_success') else 'FAILED: ' + str(exec_info.get('turn_error'))}
Tool calls in order:
{actions}
Final assistant text (delivered to user if no send_message_to_user was called): {exec_info.get('turn_response') or '(none)'}

## Deterministic checks (for reference only, not binding)
{'all passed' if checks['pass'] else 'failed: ' + '; '.join(checks['failures'])}
"""
    t0 = time.perf_counter()
    judge_model = JUDGE_MODEL or settings.interaction_agent_model
    resp = await real_llm(
        model=judge_model,
        messages=[{"role": "user", "content": user_msg}],
        system=_JUDGE_SYSTEM,
        api_key=settings.openrouter_api_key,
        tools=[_JUDGE_TOOL],
    )
    usage = resp.get("usage") or {}
    verdict: Dict[str, Any] = {"pass": None, "rationale": "", "error": None, "prompt": user_msg, "system": _JUDGE_SYSTEM,
                               "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
                               "wall_ms": round((time.perf_counter() - t0) * 1000), "model": judge_model}
    try:
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        tcs = msg.get("tool_calls") or []
        args = json.loads(tcs[0]["function"]["arguments"]) if tcs else None
        if not args:
            raise ValueError(f"judge did not call grade_run; text={msg.get('content')!r}")
        verdict["pass"] = bool(args["pass"])
        verdict["rationale"] = str(args.get("rationale", ""))
    except Exception as exc:
        verdict["error"] = repr(exc)
    return verdict


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
async def _drain_tasks() -> None:
    """Let fire-and-forget tasks (dispatch, summarizer) settle."""
    for _ in range(3):
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)


async def _execute(run: Run, tracer: Tracer, fake: FakeBatchManager) -> Dict[str, Any]:
    # steady-state compaction of the seeded history
    tracer.phase = "seed"
    while await summarize_conversation():
        pass
    wm = get_working_memory_log()
    state = wm.load_summary_state()

    tracer.phase = "probe"
    t0 = time.perf_counter()
    runtime = ia_runtime.InteractionAgentRuntime()
    if run.case.get("probe_role") == "agent":
        result = await runtime.handle_agent_message(run.case["probe"])
    else:
        result = await runtime.execute(run.case["probe"])
    await _drain_tasks()
    wall_ms = round((time.perf_counter() - t0) * 1000)

    return {
        "turn_success": result.success,
        "turn_error": result.error,
        "turn_response": result.response,
        "wall_ms": wall_ms,
        "summary_state": {
            "last_index": state.last_index,
            "summary_chars": len(state.summary_text or ""),
            "unsummarized_entries": len(state.unsummarized_entries or []),
        },
    }


def run_one(run: Run, out_dir: Path, use_judge: bool = True, max_input_tokens: int = 150_000) -> Dict[str, Any]:
    tracer = Tracer(max_input_tokens)
    fake = FakeBatchManager()

    real_ia = ia_runtime.request_chat_completion
    real_sum = summarizer_mod.request_chat_completion
    real_bm = ia_tools.get_execution_batch_manager()
    ia_runtime.request_chat_completion = tracer.wrap(real_ia, "interaction_agent")
    summarizer_mod.request_chat_completion = tracer.wrap(real_sum, "summarizer")
    ia_tools.set_execution_batch_manager(fake)

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with tempfile.TemporaryDirectory(prefix="openpoke-eval-") as tmp:
        data_dir = Path(tmp)
        try:
            redirect_stores(data_dir)
            seed(run)  # synchronous: no running loop, so no background summarizer tasks
            exec_info = asyncio.run(_execute(run, tracer, fake))
            error = None
        except Exception as exc:  # harness-level failure
            exec_info = {"turn_success": False, "turn_error": repr(exc)}
            error = repr(exc)
        finally:
            ia_runtime.request_chat_completion = real_ia
            summarizer_mod.request_chat_completion = real_sum
            ia_tools.set_execution_batch_manager(real_bm)

        conv_text = ""
        try:
            conv_text = get_conversation_log()._path.read_text(encoding="utf-8")
        except Exception:
            pass

    tool_calls = extract_tool_calls(tracer.calls)
    verdict = score(run, tool_calls, fake.dispatches)
    if not exec_info.get("turn_success", False):
        verdict["pass"] = False
        verdict["failures"].insert(0, f"turn failed: {exec_info.get('turn_error')}")

    judge: Optional[Dict[str, Any]] = None
    turn_ok = bool(exec_info.get("turn_success", False))
    if use_judge and turn_ok:
        judge = asyncio.run(judge_run(run, tool_calls, fake.dispatches, verdict["replies"], exec_info, verdict,
                                      get_settings(), real_ia))
    elif use_judge:
        judge = {"pass": False, "rationale": f"turn failed before completing: {exec_info.get('turn_error')}",
                 "error": None, "skipped": True, "input_tokens": None, "output_tokens": None, "wall_ms": 0,
                 "model": None}
    if not turn_ok:
        final_pass = False  # hard rule: a turn that raised can never pass
    else:
        final_pass = judge["pass"] if judge and judge.get("pass") is not None else verdict["pass"]

    record = {
        "run_id": run.run_id,
        "case_id": run.case["id"],
        "type": run.case["type"],
        "sweep": {"param": run.sweep_param, "value": run.sweep_value} if run.sweep_param else None,
        "started_at": started,
        "pass": final_pass,
        "judge": judge,
        "checks": {"pass": verdict["pass"], "failures": verdict["failures"]},
        "failures": verdict["failures"],
        "metrics": metrics_from(tracer.calls) | {
            "wall_ms": exec_info.get("wall_ms"),
            "gate_blocked": any("harness token gate" in (c.get("error") or "") for c in tracer.calls),
            "max_estimated_input_tokens": max((c.get("estimated_input_tokens") or 0) for c in tracer.calls) if tracer.calls else 0,
        },
        "observed": {
            "tool_calls": tool_calls,
            "dispatches": fake.dispatches,
            "replies": verdict["replies"],
            "seeded_entries": len(run.history),
            "seeded_roster_size": len(run.roster),
            "summary_state": exec_info.get("summary_state"),
        },
        "harness_error": error,
        "trace_file": f"traces/{run.run_id.replace('@', '_').replace('=', '-').replace('#', '_r')}.json",
    }

    trace_path = out_dir / record["trace_file"]
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps({
        "run_id": run.run_id,
        "case": run.case,
        "seeded_history": run.history,
        "seeded_roster": run.roster,
        "llm_calls": tracer.calls,
        "dispatches": fake.dispatches,
        "conversation_log_after": conv_text,
        "exec_info": exec_info,
        "judge": judge,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    if judge:
        record["judge"] = {k: v for k, v in judge.items() if k not in ("prompt", "system")}
    return record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", action="append", help="case id to run (repeatable)")
    ap.add_argument("--type", action="append", help="case type to run (repeatable)")
    ap.add_argument("--sweep-values", help="comma-separated override for sweep values, e.g. 20,150")
    ap.add_argument("--out", help="results directory (default: results/<timestamp>)")
    ap.add_argument("--label", default="", help="free-text label stored in results (e.g. 'baseline')")
    ap.add_argument("--no-open", action="store_true", help="do not open the HTML report when done")
    ap.add_argument("--no-judge", action="store_true", help="skip the LLM judge; pass/fail comes from deterministic checks")
    ap.add_argument("--model", default="anthropic/claude-haiku-4.5",
                    help="OpenRouter model id for the interaction agent and summarizer (default: anthropic/claude-haiku-4.5; "
                         "pass 'config' to use the server's configured model)")
    ap.add_argument("--judge-model", default="config",
                    help="judge model (default 'config' = the server's configured model, i.e. a strong grader; "
                         "pass an OpenRouter id to override, or 'same' to use --model)")
    ap.add_argument("--strategy", choices=["legacy", "budgeted"], default="legacy",
                    help="context strategy under test: legacy (baseline) or budgeted (token budget + recall_history)")
    ap.add_argument("--rpm", type=int, default=18, help="max LLM requests per minute across the run (0 = unlimited)")
    ap.add_argument("--max-input-tokens", type=int, default=150_000,
                    help="harness gate: block any LLM request whose estimated input exceeds this (never billed)")
    ap.add_argument("--repeat", type=int, default=1, help="run each case N times (run ids get a #k suffix)")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set. Put it in .env at the repo root or export it.", file=sys.stderr)
        return 2
    settings.context_strategy = args.strategy
    RATE_LIMITER.max_per_minute = args.rpm
    configured_model = settings.interaction_agent_model
    if args.model and args.model != "config":
        settings.interaction_agent_model = args.model
        settings.summarizer_model = args.model
    global JUDGE_MODEL
    if args.judge_model == "config":
        JUDGE_MODEL = configured_model
    elif args.judge_model == "same":
        JUDGE_MODEL = settings.interaction_agent_model
    else:
        JUDGE_MODEL = args.judge_model

    configure_logging()
    logging.getLogger().setLevel(logging.CRITICAL)  # turn errors are captured in results; keep stdout clean

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] in set(args.case)]
    if args.type:
        cases = [c for c in cases if c["type"] in set(args.type)]
    if not cases:
        print("no cases matched", file=sys.stderr)
        return 2

    sweep_override = [int(x) for x in args.sweep_values.split(",")] if args.sweep_values else None
    out_dir = Path(args.out) if args.out else RESULTS_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []
    for case in cases:
        for run in expand_case(case, sweep_override):
          for k in range(1, args.repeat + 1):
            if args.repeat > 1:
                run = Run(case=run.case, run_id=f"{run.run_id}#{k}", sweep_param=run.sweep_param,
                          sweep_value=run.sweep_value, history=run.history, roster=run.roster)
            print(f"▶ {run.run_id} ... ", end="", flush=True)
            rec = run_one(run, out_dir, use_judge=not args.no_judge, max_input_tokens=args.max_input_tokens)
            records.append(rec)
            m = rec["metrics"]
            status = "PASS" if rec["pass"] else "FAIL"
            print(f"{status}  rounds={m['llm_rounds']} in={m['input_tokens']} out={m['output_tokens']} wall={m['wall_ms']}ms")
            if rec.get("judge"):
                j = rec["judge"]
                print(f"    judge: {'pass' if j['pass'] else 'fail' if j['pass'] is not None else 'error'} — {j.get('rationale') or j.get('error')}")
            for f in rec["failures"]:
                print(f"    checks ✗ {f}")

    summary = {
        "label": args.label,
        "strategy": args.strategy,
        "model": settings.interaction_agent_model,
        "judge_model": None if args.no_judge else JUDGE_MODEL,
        "summarizer_model": settings.summarizer_model,
        "summary_threshold": settings.conversation_summary_threshold,
        "summary_tail": settings.conversation_summary_tail_size,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(records),
        "passed": sum(1 for r in records if r["pass"]),
        "by_type": {},
        "runs": records,
    }
    for r in records:
        bt = summary["by_type"].setdefault(r["type"], {"total": 0, "passed": 0})
        bt["total"] += 1
        bt["passed"] += int(r["pass"])

    (out_dir / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{summary['passed']}/{summary['total']} passed → {out_dir / 'results.json'}")

    from build_report import build  # same directory
    report = build(out_dir, open_browser=not args.no_open)
    print(f"report → {report}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
