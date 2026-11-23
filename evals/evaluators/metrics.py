"""Efficiency metrics computed from a recorded run (no LLM involved)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .checks import RunData

ROLE_PREFIXES = [
    ("interaction", ("You are OpenPoke",)),
    ("execution", ("You are the assistant of Poke", "You are an execution agent")),
    ("search", ("You are an expert Gmail search",)),
    ("summarizer", ("You are the assistant's chief-of-staff",)),
    ("compaction", ("You maintain the working memory of a task-execution agent",)),
    ("classifier", ("You review incoming Gmail",)),
]


def role_of(event: Dict[str, Any]) -> str:
    prefix = (event.get("system_prefix") or "").strip()
    for role, starts in ROLE_PREFIXES:
        if any(prefix.startswith(s) for s in starts):
            return role
    return "other"


def _calls(run: RunData) -> List[Dict[str, Any]]:
    """Join start/end events into one record per call."""
    by_id: Dict[int, Dict[str, Any]] = {}
    for event in run.llm_events:
        entry = by_id.setdefault(event["id"], {"id": event["id"]})
        if event.get("event") == "start":
            entry.update(start=event["t"], role=role_of(event), model=event.get("model"))
        else:
            usage = event.get("usage") or {}
            entry.update(end=event["t"], latency=event.get("latency"),
                         prompt_tokens=usage.get("prompt_tokens", 0) or 0,
                         completion_tokens=usage.get("completion_tokens", 0) or 0,
                         error=event.get("error"))
    return [c for c in by_id.values() if "start" in c]


def _in_step(call: Dict[str, Any], step: Dict[str, Any]) -> bool:
    return step["started_at"] <= call["start"] <= step.get("done_at", call["start"])


def _agents_seen_per_call(run: RunData) -> tuple[Optional[float], bool]:
    """Average number of agents visible to Poke per Poke LLM call, and whether it is exact.

    Exact when the recorder logged `agents_seen` (distinct `<agent name=...>` entries in the request).
    Otherwise approximated: the original lists every agent, so it sees the roster size at the start of
    the step; the fork sees at most 3 agents per earlier find_agents call in that step (capped at the roster).
    """
    starts = {e["id"]: e for e in run.llm_events if e.get("event") == "start"}
    ends = {e["id"]: e for e in run.llm_events if e.get("event") == "end"}
    poke = sorted((e for e in starts.values() if role_of(e) == "interaction"), key=lambda e: e["t"])
    if not poke:
        return None, True
    if all("agents_seen" in e for e in poke):
        return sum(e["agents_seen"] for e in poke) / len(poke), True

    is_fork = run.meta.get("version") == "fork"
    values = []
    for call in poke:
        step = next((s for s in run.steps if s["started_at"] <= call["t"] <= s.get("done_at", call["t"])), None)
        index = step["step"] if step else run.last_step
        roster = len(run.snapshot(index - 1)["roster"]) if index > 1 else 0
        if not is_fork:
            values.append(roster)
            continue
        searches = sum(
            (ends.get(e["id"], {}).get("tool_calls") or []).count("find_agents")
            for e in poke
            if e["t"] < call["t"] and step and step["started_at"] <= e["t"]
        )
        values.append(min(roster, 3 * searches))
    return sum(values) / len(values), False


def compute_metrics(run: RunData) -> Dict[str, Any]:
    calls = _calls(run)
    user_steps = [s for s in run.steps if s.get("kind") == "user"]
    n_turns = max(len(user_steps), 1)

    useful_reply, turn_latency = [], []
    interaction_prompt_series: List[Optional[float]] = []
    for step in user_steps:
        times = [m["observed_at"] for m in run.transcript
                 if m.get("role") == "assistant" and m.get("step") == step["step"]]
        if times:
            useful_reply.append(max(times) - step["started_at"])
        turn_latency.append(step.get("last_activity", step.get("done_at", step["started_at"])) - step["started_at"])
        poke_calls = [c for c in calls if c.get("role") == "interaction" and _in_step(c, step)]
        interaction_prompt_series.append(
            sum(c.get("prompt_tokens", 0) for c in poke_calls) / len(poke_calls) if poke_calls else None
        )

    def total(key: str, role: Optional[str] = None) -> float:
        return float(sum(c.get(key, 0) or 0 for c in calls if role is None or c.get("role") == role))

    by_role: Dict[str, Dict[str, float]] = {}
    for call in calls:
        bucket = by_role.setdefault(call.get("role", "other"), {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
        bucket["calls"] += 1
        bucket["prompt_tokens"] += call.get("prompt_tokens", 0) or 0
        bucket["completion_tokens"] += call.get("completion_tokens", 0) or 0

    agents_seen, agents_seen_exact = _agents_seen_per_call(run)
    final = run.snapshot()
    wrong_routing = len(re.findall(r"updateTrigger: [^\n]*not found", final["exec_logs"]))

    def mean(values: List[float]) -> Optional[float]:
        return sum(values) / len(values) if values else None

    return {
        "useful_reply_s": mean(useful_reply),
        "turn_latency_s": mean(turn_latency),
        "useful_reply_samples": useful_reply,
        "llm_calls_per_turn": len(calls) / n_turns,
        "prompt_tokens_per_turn": total("prompt_tokens") / n_turns,
        "completion_tokens_per_turn": total("completion_tokens") / n_turns,
        "interaction_prompt_tokens_per_call": (
            total("prompt_tokens", "interaction") / max(1, sum(1 for c in calls if c.get("role") == "interaction"))
        ),
        "interaction_prompt_series": interaction_prompt_series,
        "agents_created": len(final["roster"]),
        "agents_seen_per_call": agents_seen,
        "agents_seen_exact": agents_seen_exact,
        "wrong_agent_routing": wrong_routing,
        "llm_errors": sum(1 for c in calls if c.get("error")),
        "by_role": by_role,
    }


__all__ = ["compute_metrics", "role_of"]
