"""End-to-end overload evals: real interaction agent + real workers + fake Gmail, across a size curve.

Usage (repo root, OPENROUTER_API_KEY in .env):

    .venv/bin/python evals/e2e/run_e2e.py --estimate                  # plan + seeded token sizes, no LLM calls
    .venv/bin/python evals/e2e/run_e2e.py --case E2E-02               # one scenario at its pinned size, both strategies
    .venv/bin/python evals/e2e/run_e2e.py                             # every scenario at its pinned overflow size
    .venv/bin/python evals/e2e/run_e2e.py --sizes 0,40000,80000       # sweep mode: a size curve instead
    .venv/bin/python evals/e2e/run_e2e.py --strategy budgeted --jobs 4  # process-parallel cells

Per cell (case, size, strategy):
  1. Fresh temp data dir; every store (conversation log, working memory, roster,
     worker logs, triggers db) is redirected there.
  2. The fake Gmail world is seeded and patched in under the worker tools.
  3. History and worker logs are seeded; `size` filler tokens go into the
     conversation log and into each worker log the case marks with filler.
  4. The summarizer runs to steady state (as a long-lived deployment would).
  5. The case's user turns are sent one at a time through the real
     InteractionAgentRuntime; workers run through the real batch manager and
     call back into the interaction agent; the harness waits for quiescence.
  6. Success = deterministic checks on the final world state + replies.
     An outcome judge decides pass/fail from the final state; the rubric judge
     (judge_v2.py) grades the trajectory on 16 yes/no questions.

Isolation: cells never share on-disk state. Each cell gets its own TemporaryDirectory
and the harness redirects the conversation / working-memory / roster / worker-log /
triggers singletons into it before seeding. Fake Gmail and LLM wrappers are patched
for that cell and restored in `finally`. Sequential runs rely on that redirect+restore.
`--jobs N` (N>1) runs cells in separate processes so those process-global singletons
and monkeypatches cannot race.

Cost guards: a per-request token gate (`--context-window`, simulates the model's
window and blocks the request locally, never billed), a per-cell LLM call cap
(`--max-calls`), a per-turn wall deadline, and RPM pacing with 429 backoff.
With `--jobs N`, `--rpm` is split across workers (floor division, min 1 each).
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
import multiprocessing as mp
import random
import re
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CASES_PATH = HERE / "cases.json"
RESULTS_ROOT = HERE / "results"

from server.config import get_settings  # noqa: E402
from server.logging_config import configure_logging, logger  # noqa: E402
from server.openrouter_client import request_chat_completion as _real_llm  # noqa: E402
from server.services.conversation import get_conversation_log  # noqa: E402
from server.services.conversation.summarization import get_working_memory_log  # noqa: E402
from server.services.conversation.summarization.summarizer import summarize_conversation  # noqa: E402
from server.services.execution import get_agent_roster, get_execution_agent_logs  # noqa: E402
import server.services.triggers as triggers_pkg  # noqa: E402
import server.agents.interaction_agent.runtime as ia_runtime  # noqa: E402
import server.agents.interaction_agent.tools as ia_tools  # noqa: E402
import server.agents.execution_agent.runtime as ea_runtime  # noqa: E402
import server.agents.execution_agent.tasks.search_email.tool as search_tool  # noqa: E402
import server.context.digest as digest_mod  # noqa: E402
import server.services.conversation.summarization.summarizer as summarizer_mod  # noqa: E402
from server.agents.execution_agent.batch_manager import ExecutionBatchManager  # noqa: E402

from world import FakeGmail, install, iso_days_ago  # noqa: E402

# ---------------------------------------------------------------------------
# Filler generators (4 chars ~ 1 token)
# ---------------------------------------------------------------------------
_PAD = [
    "Also, while I remember, the office plants need watering on Thursdays and someone keeps forgetting.",
    "The parking garage is switching to the new badge readers next month, so expect a line the first morning.",
    "I still need to book the team offsite venue; the lakeside place was nice but the wifi was terrible.",
    "Reminder to self: the espresso machine descaling cycle takes forty minutes and beeps the whole time.",
    "The quarterly all-hands moved to the big auditorium because the small one has a broken projector.",
    "Someone left a very good umbrella in the lobby and nobody has claimed it in two weeks.",
    "The new hire orientation deck has a slide about the fire drill that is three years out of date.",
    "Lunch options near the new office are mostly salads and one surprisingly good taco truck.",
    "The building elevator inspection sticker expires in October, I noticed it on the way up.",
    "Weekend plan is to finally fix the shelf in the hallway that has been leaning since spring.",
]
_CONV_PAIRS = [
    ("can you remind me what time the dentist is on the 14th", "Your dentist appointment on the 14th is at 3:30pm."),
    ("did the gym renewal go through", "Yes, the gym membership renewed on the 1st for another year."),
    ("what's the wifi password at the office again", "The office wifi password is in your notes under 'IT'; I can't see it here."),
    ("any news on the lease", "No new emails about the lease since the landlord's note last week."),
    ("book me a haircut next friday", "Booked: haircut next Friday at 5pm."),
    ("what did the vet say about the cat", "The vet's follow-up says the cat's bloodwork was normal; recheck in six months."),
    ("what's on my calendar tomorrow", "Tomorrow: standup 9:30, design review 11, 1:1 with Dana at 3."),
    ("thanks", "Anytime."),
]
_WORKER_TOPICS = ["invoice from the print shop", "gym membership receipt", "lease renewal notice", "passport renewal",
                  "car service appointment", "vet follow-up", "conference hotel booking", "insurance claim",
                  "utility bill", "team lunch RSVP", "library overdue notice", "flight change notice"]
_SENDERS = ["billing@printco.com", "members@fitclub.com", "office@landlord.com", "noreply@passport.gov",
            "service@autocare.com", "frontdesk@petvet.com", "reservations@hotel.com", "claims@insureco.com"]


def _pad(text: str, approx_tokens: int, seed: int) -> str:
    if approx_tokens <= 0:
        return text
    rng = random.Random(seed)
    parts, size, target = [text], len(text), approx_tokens * 4
    while size < target:
        s = rng.choice(_PAD)
        parts.append(s)
        size += len(s) + 1
    return " ".join(parts)


def conversation_filler(total_tokens: int, entry_tokens: int = 2000) -> List[Dict[str, str]]:
    """User/reply pairs, each entry ~entry_tokens, until total_tokens is reached."""
    out: List[Dict[str, str]] = []
    produced, i = 0, 0
    while produced < total_tokens:
        u, r = _CONV_PAIRS[i % len(_CONV_PAIRS)]
        out.append({"role": "user", "content": _pad(u, entry_tokens, i * 2)})
        produced += entry_tokens
        if produced < total_tokens:
            out.append({"role": "reply", "content": _pad(r, entry_tokens, i * 2 + 1)})
            produced += entry_tokens
        i += 1
    return out


def worker_filler(total_tokens: int, block_tokens: int = 2500) -> List[Dict[str, str]]:
    """Past worker requests: request, action, big tool_response, response. Each block ~block_tokens."""
    out: List[Dict[str, str]] = []
    produced, i = 0, 0
    rng = random.Random(99)
    while produced < total_tokens:
        topic = _WORKER_TOPICS[i % len(_WORKER_TOPICS)]
        sender = _SENDERS[i % len(_SENDERS)]
        out.append({"tag": "agent_request", "content": f"Find the latest email about the {topic} and summarize it."})
        out.append({"tag": "agent_action", "content": f"Calling task_email_search with: {{\"search_query\": \"{topic}\"}}"})
        results = []
        for k in range(3):
            results.append({"id": f"f-{i}-{k}", "thread_id": f"thr-f-{i}-{k}", "subject": f"{topic.title()} ({k + 1})",
                            "sender": sender, "clean_text": _pad(f"Details regarding the {topic}.", (block_tokens - 300) // 3, i * 10 + k)})
        out.append({"tag": "tool_response", "content": "task_email_search: " + json.dumps(results)})
        out.append({"tag": "agent_response", "content": f"Latest email about the {topic} is from {sender}: routine notice, no action required. "
                                                         f"Older related emails: {rng.randint(1, 4)}."})
        produced += block_tokens
        i += 1
    return out


_THREAD_FILLER = [
    "Thanks for the quick turnaround on this. I've looped in our finance team so they can review the payment schedule in parallel.",
    "One more thing from our legal side: they'd like the governing-law clause to stay as drafted; no changes needed there.",
    "Apologies for the delay, I was travelling. Picking this back up now and will respond point by point below.",
    "Quick note that our procurement portal will need the final PDF uploaded before the 20th for this to hit the next approval cycle.",
    "I've attached the redlined version from our side; most edits are cosmetic, the substantive ones are called out in the body.",
    "Following up on the call: we're aligned on the onboarding timeline and the support SLA language as previously discussed.",
    "Our CFO asked whether invoices can be consolidated monthly rather than per order; I said I'd raise it with you.",
    "Also confirming that the data-processing addendum is unchanged from the version you reviewed last quarter.",
]


def generate_thread(kind: str, approx_tokens: int, *, party: str = "Sarah Kim", company: str = "Acme", seed: int = 5,
                    terms: Optional[Dict[str, str]] = None) -> str:
    """A long back-and-forth negotiation thread with a handful of specific terms spread through it.

    Key facts (so cases can check them): payment terms, discount, initial term, liability cap, renewal notice,
    placed at ~5%, ~30%, ~55%, ~75% and ~95% of the text so a partial read misses some.
    """
    rng = random.Random(seed)
    terms = terms or {}
    pay = terms.get("payment", "net-45")
    cap = terms.get("cap", "$500k")
    facts = [
        f"On payment terms, {company} is asking for {pay} (we had proposed {'net-30' if pay != 'net-30' else 'net-15'}).",
        f"They are offering a 2% early-payment discount if we pay within 10 days.",
        f"Initial term: {company} wants 12 months with auto-renewal.",
        f"Liability cap: {company}'s draft caps liability at {cap}; our legal wants it raised.",
        f"Renewal notice: either side must give 60 days' written notice to not renew.",
    ]
    target = max(2_000, approx_tokens) * 4
    slots = [int(target * f) for f in (0.05, 0.30, 0.55, 0.75, 0.95)]
    out: List[str] = []
    size = 0
    msg_no = 1
    fi = 0
    while size < target or fi < len(facts):
        author = party if msg_no % 2 else "me"
        body = [f"--- Message {msg_no} from {author} ---"]
        while len(" ".join(body)) < rng.randint(600, 1400):
            body.append(rng.choice(_THREAD_FILLER))
        if fi < len(facts) and size >= slots[fi]:
            body.insert(2, facts[fi])
            fi += 1
        text = "\n".join(body)
        out.append(text)
        size += len(text) + 2
        msg_no += 1
        if size >= target and fi >= len(facts):
            break
    return "\n\n".join(out)


_ROSTER_TOPICS = ["Email to", "Emails -", "Reply to", "Follow up with", "Thread with", "Contract", "Invoice", "Meeting with",
                  "Scheduling", "Reminder for", "Intro to", "Renewal", "Support ticket", "Onboarding", "Offsite"]
_ROSTER_PEOPLE = ["Sarah", "Sarah Kim", "Mike", "Mike Torres", "Jordan", "Raj", "Raj Patel", "Lena", "Dana", "Chris", "Gavin",
                  "Priya", "Omar", "Yuki", "Diego", "Aisha", "Tom", "Maria", "Chen", "Alex"]
_ROSTER_ORGS = ["Acme", "Globex", "Initech", "Umbrella", "Hooli", "Vandelay", "Stark", "Wayne", "Tyrell", "Weyland"]


def make_roster_names(count: int, seed: int = 7) -> List[str]:
    """Plausible topic+counterpart worker names, with near-duplicates of the real ones mixed in."""
    rng = random.Random(seed)
    out: List[str] = ["Sarah Email", "Emails - Sarah Kim", "Contract Sarah", "Email to Sarah K", "Sarah Kim Thread",
                      "Acme Emails", "Acme Contract", "Email to Mike", "Finance Digest", "Contract Threads"]
    seen = set(out)
    while len(out) < count:
        kind = rng.random()
        if kind < 0.6:
            name = f"{rng.choice(_ROSTER_TOPICS)} {rng.choice(_ROSTER_PEOPLE)}"
        elif kind < 0.85:
            name = f"{rng.choice(_ROSTER_ORGS)} {rng.choice(['Emails', 'Contract', 'Renewal', 'Invoice', 'Thread', 'Follow-up'])}"
        else:
            name = f"{rng.choice(_ROSTER_TOPICS)} {rng.choice(_ROSTER_PEOPLE)} {rng.randint(2, 9)}"
        if name in seen:
            name = f"{name} {len(out)}"
        seen.add(name)
        out.append(name)
    return out[:count]


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
@dataclass
class Cell:
    case: Dict[str, Any]
    size: int
    strategy: str
    run_id: str
    history: List[Dict[str, str]] = field(default_factory=list)
    worker_logs: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    seeded_tokens: Dict[str, int] = field(default_factory=dict)


def resolve_cases(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply `extends`: a case may copy another and override fields. `strip_worker_filler` drops filler markers."""
    by_id = {c["id"]: c for c in raw}
    out = []
    for c in raw:
        if "extends" in c:
            base = copy.deepcopy(by_id[c["extends"]])
            base.update({k: v for k, v in c.items() if k != "extends"})
            c = base
        if c.pop("strip_worker_filler", False):
            c["worker_logs"] = {a: [e for e in es if not e.get("filler")] for a, es in c.get("worker_logs", {}).items()}
            c["worker_logs"] = {a: es for a, es in c["worker_logs"].items() if es}
        out.append(c)
    return out


def build_cell(case: Dict[str, Any], size: int, strategy: str, rep: int, repeat: int) -> Cell:
    """`size` filler tokens go into the conversation log AND into every worker log that has a filler marker.

    Cases with `filler_entry_tokens` use smaller conversation entries (so the legacy count-based compaction fires).
    Mailbox emails whose body is {"generate": kind, "tokens": "size"} get a generated body of `size` tokens instead.
    """
    entry_tokens = int(case.get("filler_entry_tokens", 2000))

    def _gen(spec: Dict[str, Any]) -> str:
        raw = spec.get("tokens", 4000)
        if isinstance(raw, str) and raw.startswith("size"):
            div = float(raw.split("/")[1]) if "/" in raw else 1.0
            tokens = int(size / div)
        else:
            tokens = int(raw)
        return spec.get("prefix", "") + generate_thread(spec["generate"], tokens, party=spec.get("party", "Sarah Kim"),
                                                        company=spec.get("company", "Acme"), seed=spec.get("seed", 5),
                                                        terms=spec.get("terms"))

    history: List[Dict[str, str]] = []
    for h in case.get("history", []):
        if h.get("filler"):
            history.extend(conversation_filler(size, entry_tokens))
        elif isinstance(h.get("content"), dict) and "generate" in h["content"]:
            history.append({"role": h["role"], "content": _gen(h["content"])})
        else:
            history.append(h)

    worker_logs: Dict[str, List[Dict[str, str]]] = {}
    for agent, entries in case.get("worker_logs", {}).items():
        out: List[Dict[str, str]] = []
        for e in entries:
            if e.get("filler"):
                out.extend(worker_filler(size))
            else:
                out.append(e)
        worker_logs[agent] = out

    case = copy.deepcopy(case)
    mailbox_tokens = 0
    for e in case.get("world", {}).get("emails", []):
        body = e.get("body")
        if isinstance(body, dict) and "generate" in body:
            e["body"] = _gen(body)
            mailbox_tokens += len(e["body"]) // 4

    label = f"{case['id']}@{size // 1000}k"
    if repeat > 1:
        label += f"#{rep}"
    return Cell(case=case, size=size, strategy=strategy, run_id=label, history=history, worker_logs=worker_logs,
                seeded_tokens={
                    "conversation": sum(len(h["content"]) for h in history) // 4,
                    "worker_logs": sum(len(e["content"]) for es in worker_logs.values() for e in es) // 4,
                    "mailbox": mailbox_tokens,
                })


# ---------------------------------------------------------------------------
# Store redirection + seeding
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
    store = triggers_pkg._trigger_store
    store._db_path = data_dir / "triggers.db"
    store._ensure_directory()
    store._ensure_schema()


def seed(cell: Cell) -> None:
    conv = get_conversation_log()
    for h in cell.history:
        role = h["role"]
        if role == "user":
            conv.record_user_message(h["content"])
        elif role == "reply":
            conv.record_reply(h["content"])
        elif role == "agent":
            conv.record_agent_message(h["content"])
        else:
            raise ValueError(f"unknown history role {role!r}")
    roster = get_agent_roster()
    gen = cell.case.get("roster_generate")
    decoys = make_roster_names(int(gen.get("count", 100)), int(gen.get("seed", 7))) if gen else []
    for name in decoys:
        roster.add_agent(name)
    for name in cell.case.get("roster", []):
        roster.add_agent(name)
    if get_settings().budgeted_context:
        # Metadata as a long-lived deployment would have it: decoys used long ago with a generic purpose,
        # the case's real workers used recently with their seeded first request.
        from server.services.execution.roster_v2 import get_roster_meta
        import time as _time
        meta = get_roster_meta()
        meta.load()
        for i, name in enumerate(decoys):
            # spread decoys over the last 300 days; a few hundred are more recent than any aged real worker
            meta._meta[name] = {"purpose": f"Handle: {name}", "created": _time.time() - 86400 * (30 + i % 300),
                                "last_used": _time.time() - 86400 * (0.1 + (i % 300)), "runs": 1, "last_task": f"Handle: {name}", "ids": []}
        ages = cell.case.get("roster_age_days") or {}
        for name in cell.case.get("roster", []):
            first = next((e["content"] for e in (cell.worker_logs.get(name) or []) if e.get("tag") == "agent_request"), f"Handle: {name}")
            last_report = next((e["content"] for e in reversed(cell.worker_logs.get(name) or []) if e.get("tag") == "agent_response"), "")
            age_s = 86400 * float(ages.get(name, 0)) if ages.get(name) else 600
            meta._meta[name] = {"purpose": " ".join(first.split())[:140], "created": _time.time() - age_s - 3600, "last_used": _time.time() - age_s,
                                "runs": 1, "last_task": " ".join(first.split())[:200], "ids": []}
            meta.save()
            if last_report:
                meta.record_report(name, last_report)
        meta.save()
    logs = get_execution_agent_logs()
    for agent, entries in cell.worker_logs.items():
        for e in entries:
            logs._append(agent, e["tag"], e["content"])


def build_world(case: Dict[str, Any]) -> FakeGmail:
    seed_spec = copy.deepcopy(case.get("world", {}))
    for e in seed_spec.get("emails", []):
        if "date" not in e:
            e["date"] = iso_days_ago(int(e.pop("days_ago", 1)))
    return FakeGmail(seed_spec)


# ---------------------------------------------------------------------------
# Instrumentation
# ---------------------------------------------------------------------------
def estimate_tokens(system: Optional[str], messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]]) -> int:
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
    """Raised instead of calling OpenRouter when a prompt exceeds the simulated context window."""


class HarnessCallCap(Exception):
    """Raised when a cell exceeds its LLM call budget."""


class RateLimiter:
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


RATE_LIMITER = RateLimiter(30)
MAX_429_RETRIES = 6
_AGENT_NAME_RE = re.compile(r"Agent Name:\s*(.+)")


class Tracer:
    def __init__(self, context_window: int, max_calls: int) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.phase = "seed"
        self.context_window = context_window
        self.max_calls = max_calls
        self.aborted: Optional[str] = None
        self.t_start = time.monotonic()

    def wrap(self, real, component: str):
        async def _traced(*, model, messages, system=None, api_key=None, tools=None, **kw):
            snapshot = copy.deepcopy(messages)
            t0 = time.monotonic()
            error = None
            gate_blocked = False
            response: Dict[str, Any] = {}
            try:
                if self.phase != "seed" and sum(1 for c in self.calls if c["phase"] != "seed") >= self.max_calls:
                    self.aborted = f"call cap {self.max_calls} reached"
                    raise HarnessCallCap(self.aborted)
                est = estimate_tokens(system, messages, tools)
                if est > self.context_window:
                    gate_blocked = True
                    raise HarnessTokenGate(
                        f"context window exceeded: estimated {est:,} input tokens > {self.context_window:,} "
                        f"(blocked by harness before OpenRouter; emulates the provider's context_length error)")
                for attempt in range(MAX_429_RETRIES + 1):
                    await RATE_LIMITER.acquire()
                    try:
                        response = await real(model=model, messages=messages, system=system, api_key=api_key, tools=tools, **kw)
                        break
                    except Exception as exc:
                        if "429" in str(exc) and attempt < MAX_429_RETRIES:
                            await asyncio.sleep(min(60.0, 5.0 * (2 ** attempt)))
                            continue
                        raise
                return response
            except Exception as exc:
                error = repr(exc)
                raise
            finally:
                usage = response.get("usage") or {}
                msg = (response.get("choices") or [{}])[0].get("message", {}) if response else {}
                agent = None
                if component == "execution_agent" and system:
                    m = _AGENT_NAME_RE.search(system)
                    agent = m.group(1).strip() if m else None
                self.calls.append({
                    "phase": self.phase,
                    "component": component,
                    "agent": agent,
                    "model": model,
                    "t0": round(t0 - self.t_start, 3),
                    "wall_ms": round((time.monotonic() - t0) * 1000),
                    "system": system,
                    "messages": snapshot,
                    "tools": [t["function"]["name"] for t in (tools or [])],
                    "assistant_text": msg.get("content") or "",
                    "tool_calls": [{"name": tc["function"]["name"], "arguments": tc["function"].get("arguments", "")}
                                   for tc in (msg.get("tool_calls") or [])],
                    "usage": {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")},
                    "estimated_input_tokens": estimate_tokens(system, snapshot, tools),
                    "gate_blocked": gate_blocked,
                    "error": error,
                })
        return _traced


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
async def _drain(deadline_s: float) -> bool:
    """Wait for fire-and-forget tasks (workers, callbacks, summarizer). Returns False on deadline."""
    t_end = time.monotonic() + deadline_s
    while True:
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        if not pending:
            return True
        remaining = t_end - time.monotonic()
        if remaining <= 0:
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            return False
        await asyncio.wait(pending, timeout=min(remaining, 2.0), return_when=asyncio.FIRST_COMPLETED)


async def _execute(cell: Cell, tracer: Tracer, turn_timeout: float, cell_timeout: float = 0.0) -> Dict[str, Any]:
    # Steady-state compaction of the seeded history. In production this runs in the background after
    # every append and a failure is only logged, so a blocked summarizer call must not abort the cell:
    # record it and carry on with the raw log, exactly as the server would.
    tracer.phase = "seed"
    seed_error: Optional[str] = None
    for _ in range(50):
        try:
            if not await summarize_conversation():
                break
        except Exception as exc:
            seed_error = repr(exc)
            break
    state = get_working_memory_log().load_summary_state()
    conv = get_conversation_log()
    seed_entries = sum(1 for _ in conv.iter_entries())

    turns_out: List[Dict[str, Any]] = []
    t_all = time.monotonic()
    aborted: Optional[str] = None
    timed_out = False

    def _remaining() -> float:
        if cell_timeout <= 0:
            return turn_timeout
        return cell_timeout - (time.monotonic() - t_all)

    for i, text in enumerate(cell.case["turns"], start=1):
        if _remaining() <= 0:
            timed_out = True
            aborted = f"cell runtime cap {cell_timeout:.0f}s reached before turn {i}"
            break
        tracer.phase = f"turn{i}"
        t0 = time.monotonic()
        budget = min(turn_timeout, _remaining())
        runtime = ia_runtime.InteractionAgentRuntime()
        try:
            result = await asyncio.wait_for(runtime.execute(text), timeout=budget)
            ok, err = result.success, result.error
        except asyncio.TimeoutError:
            ok, err = False, f"turn {i} exceeded {budget:.0f}s"
        except Exception as exc:  # defensive: runtime normally returns a result object
            ok, err = False, repr(exc)
        settled = await _drain(max(1.0, min(turn_timeout, _remaining()) - (time.monotonic() - t0)))
        if not settled:
            err = (err + "; " if err else "") + f"turn {i} callbacks did not settle in time"
        turns_out.append({"turn": i, "text": text, "success": ok, "error": err, "wall_ms": round((time.monotonic() - t0) * 1000)})
        if tracer.aborted:
            aborted = tracer.aborted
            break
        if not settled:
            timed_out = cell_timeout > 0 and _remaining() <= 0
            aborted = f"cell runtime cap {cell_timeout:.0f}s reached" if timed_out else f"turn {i} deadline"
            break

    replies = [p for tag, _, p in list(conv.iter_entries())[seed_entries:] if tag == "poke_reply"]
    return {
        "seed_error": seed_error,
        "timed_out": timed_out,
        "turns": turns_out,
        "replies": replies,
        "aborted": aborted,
        "wall_ms": round((time.monotonic() - t_all) * 1000),
        "summary_state": {"last_index": state.last_index, "summary_chars": len(state.summary_text or ""),
                          "unsummarized_entries": len(state.unsummarized_entries or [])},
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _ci(hay: str, needle: str) -> bool:
    return needle.lower() in (hay or "").lower()


def _sent_matches(sent: Dict[str, Any], m: Dict[str, Any]) -> bool:
    cc = " ".join(sent.get("cc") or [])
    if "to_contains" in m and not _ci(sent.get("to", ""), m["to_contains"]):
        return False
    if "cc_contains" in m and not _ci(cc, m["cc_contains"]):
        return False
    if "subject_contains" in m and not _ci(sent.get("subject", ""), m["subject_contains"]):
        return False
    if "thread_id" in m and sent.get("thread_id") != m["thread_id"]:
        return False
    if "draft_id" in m and sent.get("draft_id") != m["draft_id"]:
        return False
    if "body_contains_any" in m and not any(_ci(sent.get("body", ""), n) for n in m["body_contains_any"]):
        return False
    if "body_contains_all" in m and not all(_ci(sent.get("body", ""), n) for n in m["body_contains_all"]):
        return False
    return True


def check_success(spec: Dict[str, Any], world: FakeGmail, replies: List[str], dispatched: Optional[List[str]] = None) -> Tuple[bool, Dict[str, Any], List[str]]:
    snap = world.snapshot()
    dispatched = dispatched or []
    checks: Dict[str, Any] = {}
    failures: List[str] = []
    joined = "\n".join(replies)

    for i, m in enumerate(spec.get("sent", [])):
        ok = any(_sent_matches(s, m) for s in snap["sent"])
        checks[f"sent[{i}]"] = ok
        if not ok:
            failures.append(f"no sent message matching {json.dumps(m)} (sent: {len(snap['sent'])})")
    if "sent_count_max" in spec:
        ok = len(snap["sent"]) <= spec["sent_count_max"]
        checks["sent_count_max"] = ok
        if not ok:
            failures.append(f"{len(snap['sent'])} messages sent, max {spec['sent_count_max']}")
    if "drafts_created_max" in spec:
        ok = snap["drafts_created"] <= spec["drafts_created_max"]
        checks["drafts_created_max"] = ok
        if not ok:
            failures.append(f"{snap['drafts_created']} drafts created, max {spec['drafts_created_max']}")
    if "dispatched_agents_include" in spec:
        missing = [a for a in spec["dispatched_agents_include"] if a not in dispatched]
        checks["dispatched_agents_include"] = not missing
        if missing:
            failures.append(f"expected dispatch to {missing}; dispatched {dispatched or 'none'}")
    if "reply_contains_any" in spec:
        ok = any(_ci(joined, n) for n in spec["reply_contains_any"])
        checks["reply_contains_any"] = ok
        if not ok:
            failures.append(f"no reply contains any of {spec['reply_contains_any']}")
    if "reply_contains_all" in spec:
        missing = [n for n in spec["reply_contains_all"] if not _ci(joined, n)]
        checks["reply_contains_all"] = not missing
        if missing:
            failures.append(f"replies missing {missing}")
    if "reply_not_contains_any" in spec:
        bad = [n for n in spec["reply_not_contains_any"] if _ci(joined, n)]
        checks["reply_not_contains_any"] = not bad
        if bad:
            failures.append(f"reply contains forbidden {bad}")
    return (not failures), checks, failures


def counters(tracer: Tracer, world: FakeGmail, roster_before: List[str]) -> Dict[str, Any]:
    probe = [c for c in tracer.calls if c["phase"] != "seed"]
    seed_blocked = sum(1 for c in tracer.calls if c["phase"] == "seed" and c["gate_blocked"])
    by_comp: Dict[str, int] = {}
    for c in probe:
        by_comp[c["component"]] = by_comp.get(c["component"], 0) + 1
    ia_tool_calls = [tc for c in probe if c["component"] == "interaction_agent" for tc in c["tool_calls"]]
    dispatches = [tc for tc in ia_tool_calls if tc["name"] == "send_message_to_agent"]
    recalls = [tc for tc in ia_tool_calls if tc["name"] == "recall_history"]
    seen, dups = set(), 0
    for call in world.calls:
        key = (call["tool"], json.dumps(call["args"], sort_keys=True))
        if key in seen:
            dups += 1
        seen.add(key)
    billed = [c for c in probe if not c["gate_blocked"] and not c["error"]]
    prompt_tokens = [c["usage"]["prompt_tokens"] or c["estimated_input_tokens"] for c in probe]
    roster_after = get_agent_roster().get_agents()
    return {
        "llm_calls": len(probe),
        "llm_calls_by_component": by_comp,
        "seed_llm_calls": len(tracer.calls) - len(probe),
        "ia_tool_calls": len(ia_tool_calls),
        "worker_tool_calls": len(world.calls),
        "steps": len(ia_tool_calls) + len(world.calls),
        "dispatches": len(dispatches),
        "recalls": len(recalls),
        "new_workers": [a for a in roster_after if a not in roster_before],
        "duplicate_worker_tool_calls": dups,
        "input_tokens": sum((c["usage"]["prompt_tokens"] or c["estimated_input_tokens"]) for c in billed),
        "output_tokens": sum((c["usage"]["completion_tokens"] or 0) for c in billed),
        "blocked_input_tokens_est": sum(c["estimated_input_tokens"] for c in probe if c["gate_blocked"]),
        "max_prompt_tokens": max(prompt_tokens) if prompt_tokens else 0,
        "gate_blocks": sum(1 for c in probe if c["gate_blocked"]) + seed_blocked,
        "seed_gate_blocks": seed_blocked,
        "llm_errors": sum(1 for c in probe if c["error"] and not c["gate_blocked"]),
        "llm_wall_ms": sum(c["wall_ms"] for c in probe),
    }


def fail_reason(success: bool, exec_info: Dict[str, Any], cnt: Dict[str, Any], bucket: Optional[str] = None) -> Optional[str]:
    if success:
        return None
    if exec_info.get("timed_out"):
        return "timeout"
    if cnt["gate_blocks"]:
        return "overflow"
    if exec_info.get("aborted"):
        return "loop"
    if any("iteration limit" in (t.get("error") or "") for t in exec_info["turns"]):
        return "loop"
    if cnt["llm_errors"] or any(t.get("error") for t in exec_info["turns"]):
        return "error"
    return bucket or "quality"


# ---------------------------------------------------------------------------
# Outcome judge: final state only, can veto a deterministic pass
# ---------------------------------------------------------------------------
_OUTCOME_TOOL = {
    "type": "function",
    "function": {
        "name": "grade_outcome",
        "description": "Grade the final state left behind by the run.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_done": {"type": "boolean", "description": "The user's request was fulfilled in the final state."},
                "reply_accurate": {"type": "boolean", "description": "What the user was told matches the final state (nothing claimed that did not happen, nothing wrong stated)."},
                "side_effects": {
                    "type": "array",
                    "items": {"type": "object", "properties": {
                        "severity": {"type": "string", "enum": ["major", "minor"]},
                        "what": {"type": "string"}},
                        "required": ["severity", "what"], "additionalProperties": False},
                    "description": "Anything left behind that the user did not ask for. major = the user would have to clean it up or was misled (extra/duplicate drafts, extra sends, wrong recipient or cc, missing cc, false claims); minor = cosmetic.",
                },
                "reason": {"type": "string", "description": "One or two sentences."},
            },
            "required": ["task_done", "reply_accurate", "side_effects", "reason"],
            "additionalProperties": False,
        },
    },
}

_OUTCOME_SYSTEM = """You audit the END STATE of an email-assistant run. You do not see the steps, only what is left behind.

You are given the user's request (their turns), the mailbox before and after (drafts that existed before are marked seeded; sent messages and drafts created during the run are the run's doing), and the replies the user saw. Decide:
- task_done: is the request fulfilled in the final state?
- reply_accurate: does what the user was told match the state? Claiming "sent" when nothing was sent, or stating a figure not supported by the mailbox, is inaccurate.
- side_effects: list everything left behind that the request did not call for. Severity major when the user would have to clean it up or was misled: a duplicate or stray draft, more than one send, a wrong or missing recipient/cc, a send the user did not confirm, a false claim. Severity minor for cosmetic issues (tone, subject wording, an extra courtesy line). A single draft that was then sent is not a side effect. A draft shown to the user and awaiting their confirmation is not a side effect. A draft that was created and then deleted within the run leaves nothing behind and is not a side effect (wasted steps are judged elsewhere). A draft marked seeded existed before the run: leaving it untouched is never a side effect unless the user asked for it to be removed.
Be literal and strict about state; do not infer good intentions. Call grade_outcome exactly once."""


async def outcome_judge(case: Dict[str, Any], snap: Dict[str, Any], replies: List[str], checks_ok: bool, failures: List[str],
                        api_key: str, model: Optional[str] = None) -> Dict[str, Any]:
    model = model or JUDGE_MODEL
    seed = case.get("world", {})
    before = [f"  - draft {d['id']} to={d['to']} cc={d.get('cc', [])} thread={d.get('thread_id')} subject={_short(d['subject'], 60)} (seeded)" for d in seed.get("drafts", [])]
    after = [f"sent ({len(snap['sent'])}):"]
    for m in snap["sent"]:
        after.append(f"  - to={m['to']} cc={m['cc']} thread={m['thread_id']} via={m['via']} draft={m.get('draft_id')} subject={_short(m['subject'], 60)} body={_short(m['body'], 240)}")
    after.append(f"drafts remaining ({len(snap['drafts'])}), created during run: {snap['drafts_created']}, deleted during run: {snap['deleted_drafts']}")
    for d in snap["drafts"]:
        after.append(f"  - {d['id']} to={d['to']} cc={d['cc']} thread={d['thread_id']} subject={_short(d['subject'], 60)} {'(seeded)' if d.get('created_by_seed') else '(created during run)'} body={_short(d['body'], 160)}")
    prompt = "\n".join([
        f"CASE {case['id']} {case['name']}: {case['description']}",
        "", "USER TURNS (in order): " + json.dumps(case["turns"]),
        "", "EXPECTED OUTCOME: " + case.get("expected_outcome", "(not specified; infer from the turns)"),
        "", "STANDING RULES OR FACTS FROM EARLIER HISTORY (non-filler entries):",
        *([f"  [{h['role']}] {_short(h['content'], 300)}" for h in case.get("history", []) if not h.get("filler")] or ["  (none)"]),
        "", "MAILBOX BEFORE THE RUN:", *(before or ["  (no drafts)"]),
        "", "MAILBOX AFTER THE RUN:", *after,
        "", "REPLIES THE USER SAW (complete):", *([f"  - {_short(r, 2500)}" for r in replies] or ["  (none)"]),
        "", f"MECHANICAL CHECKS (hints only, not the verdict): {'all passed' if checks_ok else 'failed: ' + '; '.join(failures)}",
    ])
    try:
        resp = await _real_llm(model=model, messages=[{"role": "user", "content": prompt}], system=_OUTCOME_SYSTEM,
                               api_key=api_key, tools=[_OUTCOME_TOOL], max_tokens=1500)
        msg = (resp.get("choices") or [{}])[0].get("message", {})
        for tc in msg.get("tool_calls") or []:
            if tc["function"]["name"] == "grade_outcome":
                args = tc["function"]["arguments"]
                v = json.loads(args) if isinstance(args, str) else args
                v["model"] = model
                v["major"] = [x["what"] for x in v.get("side_effects", []) if x.get("severity") == "major"]
                v["prompt"] = prompt
                return v
        return {"error": "no grade_outcome call", "model": model, "prompt": prompt, "major": []}
    except Exception as exc:
        return {"error": repr(exc), "model": model, "prompt": prompt, "major": []}


def combine_verdict(checks_ok: bool, outcome: Optional[Dict[str, Any]]) -> Tuple[bool, List[str], Optional[str]]:
    """The outcome judge decides pass/fail. Mechanical checks are hints. Falls back to checks if the judge is off/errored.

    Returns (success, reasons, fail_bucket) where fail_bucket is 'quality' or 'side_effect'.
    """
    if not outcome or outcome.get("error"):
        return checks_ok, ([] if checks_ok else ["mechanical checks failed (judge unavailable)"]), (None if checks_ok else "quality")
    reasons: List[str] = []
    if not outcome.get("task_done"):
        reasons.append(f"outcome judge: task not done — {outcome.get('reason', '')}")
    if outcome.get("reply_accurate") is False:
        reasons.append("outcome judge: reply did not match the final state")
    reasons.extend(f"side effect: {w}" for w in outcome.get("major", []))
    if not reasons:
        return True, [], None
    bucket = "side_effect" if outcome.get("task_done") and outcome.get("reply_accurate") is not False else "quality"
    return False, reasons, bucket


# ---------------------------------------------------------------------------
# Trajectory judge
# ---------------------------------------------------------------------------
def _short(s: Any, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + f"… [+{len(s) - n} chars]"


def event_log(tracer: Tracer, world: FakeGmail) -> List[str]:
    events: List[Tuple[float, str]] = []
    for c in tracer.calls:
        if c["phase"] == "seed" and not c["gate_blocked"]:
            continue
        who = c["component"] if not c["agent"] else f"worker '{c['agent']}'"
        if c["gate_blocked"]:
            events.append((c["t0"], f"[{c['phase']}] {who}: REQUEST BLOCKED — {_short(c['error'], 160)}"))
            continue
        if c["error"]:
            events.append((c["t0"], f"[{c['phase']}] {who}: LLM ERROR — {_short(c['error'], 160)}"))
            continue
        parts = []
        if c["assistant_text"]:
            parts.append(f'text="{_short(c["assistant_text"], 240)}"')
        for tc in c["tool_calls"]:
            parts.append(f"{tc['name']}({_short(tc['arguments'], 320)})")
        events.append((c["t0"], f"[{c['phase']}] {who} ({c['usage']['prompt_tokens'] or c['estimated_input_tokens']} tok in): "
                               + ("; ".join(parts) if parts else "(empty response)")))
    for call in world.calls:
        t = call["t"] - tracer.t_start
        events.append((t, f"[gmail] {call['tool']} {_short(call['args'], 240)} → {_short(call['result_brief'], 160)}"))
    events.sort(key=lambda e: e[0])
    return [e[1] for e in events]


JUDGE_MODEL = "anthropic/claude-haiku-4.5"


# ---------------------------------------------------------------------------
# One cell
# ---------------------------------------------------------------------------
def run_cell(cell: Cell, out_dir: Path, *, use_judge: bool, context_window: int, max_calls: int,
             turn_timeout: float, worker_timeout: float, cell_timeout: float = 0.0) -> Dict[str, Any]:
    settings = get_settings()
    settings.context_strategy = cell.strategy
    tracer = Tracer(context_window, max_calls)
    world = build_world(cell.case)

    saved = (ia_runtime.request_chat_completion, summarizer_mod.request_chat_completion,
             ea_runtime.request_chat_completion, search_tool.request_chat_completion,
             ia_tools.get_execution_batch_manager(),
             digest_mod.request_chat_completion)
    ia_runtime.request_chat_completion = tracer.wrap(saved[0], "interaction_agent")
    summarizer_mod.request_chat_completion = tracer.wrap(saved[1], "summarizer")
    ea_runtime.request_chat_completion = tracer.wrap(saved[2], "execution_agent")
    search_tool.request_chat_completion = tracer.wrap(saved[3], "email_search")
    digest_mod.request_chat_completion = tracer.wrap(saved[5], "digest")
    ia_tools.set_execution_batch_manager(ExecutionBatchManager(timeout_seconds=int(worker_timeout)))

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record: Dict[str, Any] = {"run_id": cell.run_id, "case_id": cell.case["id"], "name": cell.case["name"],
                              "size": cell.size, "strategy": cell.strategy, "started_at": started,
                              "seeded_tokens": cell.seeded_tokens}
    outcome: Optional[Dict[str, Any]] = None
    with tempfile.TemporaryDirectory(prefix="openpoke-e2e-") as tmp:
        try:
            redirect_stores(Path(tmp))
            seed(cell)
            roster_before = list(get_agent_roster().get_agents())
            with install(world):
                exec_info = asyncio.run(_execute(cell, tracer, turn_timeout, cell_timeout))
                cnt = counters(tracer, world, roster_before)
                dispatched_names = []
                for c in tracer.calls:
                    if c["phase"] != "seed" and c["component"] == "interaction_agent":
                        for tc in c["tool_calls"]:
                            if tc["name"] == "send_message_to_agent":
                                try:
                                    dispatched_names.append(json.loads(tc["arguments"]).get("agent_name"))
                                except Exception:
                                    pass
                checks_ok, checks, failures = check_success(cell.case.get("success", {}), world, exec_info["replies"], dispatched_names)
                # Hard failure: a blocked request or an aborted run is a fail with no grading. Judges only run
                # when the system actually completed its work, so their verdict is about quality, not overflow.
                hard_fail = None
                if exec_info.get("timed_out"):
                    hard_fail = f"timeout: cell exceeded the {cell_timeout:.0f}s runtime cap (> cap); run cancelled"
                elif cnt["gate_blocks"]:
                    hard_fail = f"overflow: {cnt['gate_blocks']} request(s) blocked at the {tracer.context_window:,}-token window"
                    if cnt.get("seed_gate_blocks"):
                        hard_fail += f" ({cnt['seed_gate_blocks']} of them the summarizer during compaction; compaction stuck, raw log carried forward)"
                elif exec_info.get("aborted"):
                    hard_fail = f"aborted: {exec_info['aborted']}"
                if hard_fail:
                    success, reasons, bucket = False, [hard_fail], None
                else:
                    if use_judge:
                        outcome = asyncio.run(outcome_judge(cell.case, world.snapshot(), exec_info["replies"], checks_ok, failures,
                                                            settings.openrouter_api_key))
                    success, reasons, bucket = combine_verdict(checks_ok, outcome)
                failures = [f"check: {f}" for f in failures] + reasons
                reason = fail_reason(success, exec_info, cnt, bucket)
                events = event_log(tracer, world)
            record.update({
                "success": success, "checks_pass": checks_ok, "fail_reason": reason, "checks": checks, "failures": failures,
                "timed_out": bool(exec_info.get("timed_out")), "cell_timeout_s": cell_timeout,
                "outcome": {k: v for k, v in outcome.items() if k != "prompt"} if outcome else None,
                "turns": exec_info["turns"], "aborted": exec_info["aborted"], "replies": exec_info["replies"],
                "seed_error": exec_info.get("seed_error"),
                "wall_ms": exec_info["wall_ms"], "summary_state": exec_info["summary_state"],
                "counters": cnt, "world": world.snapshot(), "events": events,
            })
        except Exception as exc:
            logger.exception("harness failure")
            record.update({"success": False, "fail_reason": "harness", "failures": [f"harness: {exc!r}"], "checks": {},
                           "turns": [], "replies": [], "counters": {}, "world": world.snapshot(), "events": [], "judge": None})
        finally:
            ia_runtime.request_chat_completion = saved[0]
            summarizer_mod.request_chat_completion = saved[1]
            ea_runtime.request_chat_completion = saved[2]
            search_tool.request_chat_completion = saved[3]
            ia_tools.set_execution_batch_manager(saved[4])
            digest_mod.request_chat_completion = saved[5]

    # Rubric judge (v2): harness questions from the trace + judge questions; independent of the v1 verdict.
    v2_prompt = None
    if record.get("counters"):
        try:
            import judge_v2
            v2 = judge_v2.grade(record, tracer.calls, world.calls, cell.case, model=JUDGE_MODEL,
                                api_key=settings.openrouter_api_key, use_llm=use_judge and not record.get("fail_reason") in ("overflow", "loop", "error", "timeout"))
            v2_prompt = v2.pop("prompt", None)
            record["judge_v2"] = v2
        except Exception as exc:
            record["judge_v2"] = {"error": repr(exc), "score": None, "questions": []}

    traces = out_dir / "traces"
    traces.mkdir(exist_ok=True)
    trace_path = traces / f"{cell.run_id.replace('@', '_').replace('#', '-')}_{cell.strategy}.json"
    trace_path.write_text(json.dumps({"record": record, "judge_v2_prompt": v2_prompt,
                                      "outcome_prompt": (outcome or {}).get("prompt"),
                                      "llm_calls": tracer.calls, "world_calls": world.calls,
                                      "seeded_history_tail": cell.history[-6:], "seeded_worker_logs": {
                                          a: [e for e in es if "Find the latest email about the" not in e["content"]][:8]
                                          for a, es in cell.worker_logs.items()}},
                                     ensure_ascii=False, default=str), encoding="utf-8")
    record["trace_file"] = str(trace_path.relative_to(out_dir))
    return record


# ---------------------------------------------------------------------------
# Parallel workers (separate processes: singletons + monkeypatches stay isolated)
# ---------------------------------------------------------------------------
def _apply_harness_settings(cfg: Dict[str, Any]) -> None:
    """Apply the same Settings / globals mutations main() would, inside a worker process."""
    settings = get_settings()
    settings.interaction_digest_enabled = bool(cfg["interaction_digest_enabled"])
    settings.roster_v2_enabled = bool(cfg["roster_v2_enabled"])
    if cfg["model"] != "config":
        settings.interaction_agent_model = cfg["model"]
        settings.execution_agent_model = cfg["model"]
        settings.execution_agent_search_model = cfg["model"]
        settings.summarizer_model = cfg["model"]
    global JUDGE_MODEL
    JUDGE_MODEL = cfg["judge_model"]
    RATE_LIMITER.max_per_minute = int(cfg["rpm"])
    settings.summarizer_batch_max_tokens = int(cfg["summarizer_batch_max_tokens"])
    if settings.context_budget_tokens > int(cfg["context_window"]) // 2:
        settings.context_budget_tokens = int(cfg["context_window"]) // 2
    configure_logging()
    logging.getLogger().setLevel(logging.CRITICAL)


def _parallel_cell_worker(job: Dict[str, Any]) -> Dict[str, Any]:
    """Child-process entry: one cell, own temp dir via run_cell, return the record."""
    _apply_harness_settings(job["cfg"])
    cell = Cell(**job["cell"])
    return run_cell(
        cell,
        Path(job["out_dir"]),
        use_judge=bool(job["use_judge"]),
        context_window=int(job["cfg"]["context_window"]),
        max_calls=int(job["max_calls"]),
        turn_timeout=float(job["turn_timeout"]),
        worker_timeout=float(job["worker_timeout"]),
        cell_timeout=float(job["cell_timeout"]),
    )


def _print_cell_result(rec: Dict[str, Any], cell_timeout: float) -> None:
    cnt = rec.get("counters") or {}
    status = "PASS" if rec["success"] else f"FAIL({rec['fail_reason']})"
    wall = f"> {cell_timeout:.0f}s cap" if rec.get("timed_out") else f"{rec.get('wall_ms', '?')}ms"
    print(f"{status:14} calls={cnt.get('llm_calls', '?')} steps={cnt.get('steps', '?')} "
          f"in={cnt.get('input_tokens', '?')} max={cnt.get('max_prompt_tokens', '?')} wall={wall}")
    for f in rec.get("failures", []):
        print(f"    ✗ {f}")
    o = rec.get("outcome") or {}
    if o and not o.get("error"):
        print(f"    outcome: done={o.get('task_done')} accurate={o.get('reply_accurate')} "
              f"side_effects={[(x['severity'], x['what'][:60]) for x in o.get('side_effects', [])] or 'none'}")
    v2 = rec.get("judge_v2") or {}
    if v2.get("questions"):
        nos = [q["id"] for q in v2["questions"] if q["answer"] == "no"]
        print(f"    rubric: {v2['score']}% ({v2['earned']}/{v2['applicable']}) no={nos or '-'}")


def _harness_cfg(args, settings, *, rpm: int) -> Dict[str, Any]:
    return {
        "model": args.model,
        "judge_model": JUDGE_MODEL,
        "context_window": args.context_window,
        "rpm": rpm,
        "summarizer_batch_max_tokens": settings.summarizer_batch_max_tokens,
        "interaction_digest_enabled": settings.interaction_digest_enabled,
        "roster_v2_enabled": settings.roster_v2_enabled,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", action="append", help="case id (repeatable)")
    ap.add_argument("--sizes", default=None, help="sweep mode: comma-separated filler sizes for every case (default: each case's own pinned size)")
    ap.add_argument("--strategy", choices=["legacy", "budgeted", "both"], default="both")
    ap.add_argument("--model", default="deepseek/deepseek-v4-flash",
                    help="OpenRouter model for both agents, the search sub-agent and the summarizer ('config' = server settings)")
    ap.add_argument("--judge-model", default="anthropic/claude-haiku-4.5",
                    help="judge model for all three judges (default anthropic/claude-haiku-4.5; 'config' = server's interaction model, 'same' = --model)")
    ap.add_argument("--context-window", type=int, default=64_000,
                    help="simulated model context window: any request estimated above this is blocked locally (never billed). "
                         "Scenario sizes in cases.json are pinned against 64k.")
    ap.add_argument("--summarizer-batch-tokens", type=int, default=None,
                    help="budgeted: summarizer batch cap (default: min(server setting, context-window/2) so the fix is not tested at a setting that overflows by construction)")
    ap.add_argument("--max-calls", type=int, default=80, help="LLM call cap per cell (excluding seed summarization); a safety net, the rubric's call-count question is the quality metric")
    ap.add_argument("--turn-timeout", type=float, default=300.0, help="seconds allowed per user turn incl. callbacks")
    ap.add_argument("--cell-timeout", type=float, default=240.0,
                    help="runtime cap per cell in seconds; on expiry everything in flight is cancelled and the cell is "
                         "reported as FAIL(timeout) with time shown as '> cap' (0 = no cap)")
    ap.add_argument("--worker-timeout", type=float, default=180.0, help="batch manager per-worker timeout")
    ap.add_argument("--rpm", type=int, default=60)
    ap.add_argument("--jobs", type=int, default=1,
                    help="run up to N cells in parallel as separate processes (default 1 = sequential). "
                         "Needed because each cell redirects process-global store singletons and monkeypatches Gmail/LLM. "
                         "--rpm is split across workers.")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--label", default="")
    ap.add_argument("--out")
    ap.add_argument("--resume", action="store_true", help="with --out: skip cells already recorded in that results.json")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--estimate", action="store_true", help="print the plan and seeded token sizes; make no LLM calls")
    ap.add_argument("--include-hard", action="store_true", help="also run cases marked tier=hard (skipped by default unless named with --case)")
    ap.add_argument("--no-digest-entry", action="store_true", help="ablation: budgeted strategy without the interaction agent's digest_entry tool")
    ap.add_argument("--no-roster-v2", action="store_true", help="ablation: budgeted strategy with the legacy roster rendering and no find_worker")
    args = ap.parse_args()

    settings = get_settings()
    if not args.estimate and not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set.", file=sys.stderr)
        return 2
    settings.interaction_digest_enabled = not args.no_digest_entry
    settings.roster_v2_enabled = not args.no_roster_v2
    configured_model = settings.interaction_agent_model
    if args.model != "config":
        settings.interaction_agent_model = args.model
        settings.execution_agent_model = args.model
        settings.execution_agent_search_model = args.model
        settings.summarizer_model = args.model
    global JUDGE_MODEL
    JUDGE_MODEL = configured_model if args.judge_model == "config" else (
        settings.interaction_agent_model if args.judge_model == "same" else args.judge_model)
    jobs = max(1, int(args.jobs))
    rpm_per_worker = max(1, args.rpm // jobs) if jobs > 1 else args.rpm
    RATE_LIMITER.max_per_minute = rpm_per_worker if jobs == 1 else args.rpm
    cap = args.summarizer_batch_tokens or min(settings.summarizer_batch_max_tokens, args.context_window // 2)
    settings.summarizer_batch_max_tokens = cap
    if settings.context_budget_tokens > args.context_window // 2:
        settings.context_budget_tokens = args.context_window // 2  # keep the fixed budget sane on small windows
    configure_logging()
    logging.getLogger().setLevel(logging.CRITICAL)

    cases = resolve_cases(json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"])
    if args.case:
        cases = [c for c in cases if c["id"] in set(args.case)]
    elif not args.include_hard:
        cases = [c for c in cases if c.get("tier") not in ("hard", "disabled")]
    if not cases:
        print("no cases matched", file=sys.stderr)
        return 2
    sweep = [int(s) for s in args.sizes.split(",")] if args.sizes else None
    strategies = ["legacy", "budgeted"] if args.strategy == "both" else [args.strategy]

    plan: List[Cell] = []
    for case in cases:
        sizes = sweep or [int(case.get("size", 0))]
        for size in sizes:
            for strat in strategies:
                for rep in range(1, args.repeat + 1):
                    plan.append(build_cell(case, size, strat, rep, args.repeat))

    if args.estimate:
        print(f"{len(plan)} cells; model={settings.interaction_agent_model}; judge={JUDGE_MODEL}; "
              f"window={args.context_window:,}; jobs={jobs}")
        for c in plan:
            print(f"  {c.run_id:16} {c.strategy:9} target={c.case.get('target', '?')}")
            print(f"  {c.run_id:16} {c.strategy:9} conv≈{c.seeded_tokens['conversation']:>7,} tok  worker≈{c.seeded_tokens['worker_logs']:>7,} tok  "
                  f"mailbox≈{c.seeded_tokens.get('mailbox', 0):>7,} tok  entries={sum(1 for _ in c.history)}  turns={len(c.case['turns'])}")
        return 0

    out_dir = Path(args.out) if args.out else RESULTS_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    records: List[Dict[str, Any]] = []
    done_keys = set()
    if args.resume and (out_dir / "results.json").exists():
        prev = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
        records = prev.get("runs", [])
        done_keys = {(r["run_id"], r["strategy"]) for r in records}
        print(f"resuming: {len(records)} cell(s) already in {out_dir}")

    pending = [c for c in plan if (c.run_id, c.strategy) not in done_keys]
    if jobs > 1 and pending:
        print(f"parallel: {len(pending)} cell(s) across {jobs} processes; rpm≈{rpm_per_worker}/worker "
              f"(total --rpm {args.rpm})")
        cfg = _harness_cfg(args, settings, rpm=rpm_per_worker)
        jobs_payload = [
            {
                "cell": asdict(cell),
                "out_dir": str(out_dir),
                "use_judge": not args.no_judge,
                "max_calls": args.max_calls,
                "turn_timeout": args.turn_timeout,
                "worker_timeout": args.worker_timeout,
                "cell_timeout": args.cell_timeout,
                "cfg": cfg,
            }
            for cell in pending
        ]
        # spawn: each child is a fresh interpreter so store redirects / Gmail patches cannot collide
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=min(jobs, len(jobs_payload)), mp_context=ctx) as pool:
            futures = {pool.submit(_parallel_cell_worker, job): job for job in jobs_payload}
            for fut in as_completed(futures):
                job = futures[fut]
                cell_meta = job["cell"]
                print(f"▶ {cell_meta['run_id']:16} {cell_meta['strategy']:9} ... ", end="", flush=True)
                try:
                    rec = fut.result()
                except Exception as exc:
                    rec = {
                        "run_id": cell_meta["run_id"], "case_id": cell_meta["case"]["id"],
                        "name": cell_meta["case"]["name"], "size": cell_meta["size"],
                        "strategy": cell_meta["strategy"], "success": False, "fail_reason": "harness",
                        "failures": [f"parallel worker: {exc!r}"], "checks": {}, "turns": [],
                        "replies": [], "counters": {}, "events": [],
                    }
                    print(f"FAIL(harness)  {exc!r}")
                else:
                    _print_cell_result(rec, args.cell_timeout)
                records.append(rec)
                _write_results(out_dir, records, args, settings, plan)
    else:
        RATE_LIMITER.max_per_minute = args.rpm
        for cell in pending:
            print(f"▶ {cell.run_id:16} {cell.strategy:9} ... ", end="", flush=True)
            rec = run_cell(cell, out_dir, use_judge=not args.no_judge, context_window=args.context_window,
                           max_calls=args.max_calls, turn_timeout=args.turn_timeout, worker_timeout=args.worker_timeout,
                           cell_timeout=args.cell_timeout)
            records.append(rec)
            _print_cell_result(rec, args.cell_timeout)
            _write_results(out_dir, records, args, settings, plan)

    _write_results(out_dir, records, args, settings, plan)
    try:
        import build_report
        build_report.build(out_dir, open_browser=not args.no_open)
    except Exception as exc:
        print(f"report build failed: {exc!r}", file=sys.stderr)
    print(f"\nresults: {out_dir}")
    return 0


def _write_results(out_dir: Path, records: List[Dict[str, Any]], args, settings, plan: List[Cell]) -> None:
    meta = {
        "label": args.label + (" (no digest_entry)" if args.no_digest_entry else "") + (" (no roster v2)" if args.no_roster_v2 else ""), "model": settings.interaction_agent_model, "judge_model": JUDGE_MODEL,
        "context_window": args.context_window, "max_calls": args.max_calls, "cell_timeout_s": args.cell_timeout,
        "context_budget_tokens": settings.context_budget_tokens, "summarizer_batch_max_tokens": settings.summarizer_batch_max_tokens,
        "sizes": [int(s) for s in args.sizes.split(",")] if args.sizes else sorted({c.size for c in plan}),
        "mode": "sweep" if args.sizes else "scenario",
        "strategies": sorted({c.strategy for c in plan}), "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(records), "passed": sum(1 for r in records if r["success"]),
    }
    (out_dir / "results.json").write_text(json.dumps({**meta, "runs": records}, ensure_ascii=False, indent=1, default=str),
                                          encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
