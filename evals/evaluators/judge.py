"""LLM-as-judge: one 1-5 reply-quality score per run (evaluation-plan §5b)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import httpx

from .checks import RunData, _local

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You grade a personal assistant's replies in a scripted test conversation.

Deterministic checks already verify the final reminder state. You judge REPLY QUALITY only: were the
assistant's messages to the user correct and clear? Consider: confirming the right time/schedule, asking
when information is missing or genuinely ambiguous (instead of guessing), explaining problems, answering
questions accurately, not contradicting the final reminder state.

Score 1-5:
5 = every reply correct and clear
4 = correct, minor clarity issues
3 = mostly correct, one notable mistake or confusing reply
2 = several mistakes, or one that would mislead the user
1 = wrong or unhelpful throughout

Respond with JSON only: {"justification": "<2-4 sentences>", "score": <1-5>}"""


def _render(run: RunData, focus: str) -> str:
    lines: List[str] = []
    for step in run.steps:
        if step.get("kind") == "user":
            lines.append(f"\n[step {step['step']}] USER: {step['text']}")
        else:
            lines.append(f"\n[step {step['step']}] (reminders fired: {step.get('selector')})")
        for message in run.transcript:
            if message.get("role") == "assistant" and message.get("step") == step["step"]:
                lines.append(f"ASSISTANT: {message.get('content', '')}")

    triggers = []
    for row in run.snapshot()["triggers"]:
        local = _local(row.get("next_trigger"), run.tz)
        triggers.append(
            f"- payload={row.get('payload')!r} status={row.get('status')} "
            f"next={local.strftime('%a %Y-%m-%d %H:%M') if local else None} "
            f"recurrence={row.get('recurrence_rule')!r}"
        )
    from datetime import datetime
    from zoneinfo import ZoneInfo

    started = datetime.fromisoformat(run.meta["run_start"]).astimezone(ZoneInfo(run.tz))
    return (
        f"User timezone: {run.tz}. Test started (user's local time): {started.strftime('%A %Y-%m-%d %H:%M')}. "
        "Resolve relative dates like 'tomorrow' or 'in 5 days' from this local date.\n"
        f"Focus for this case: {focus}\n\nTRANSCRIPT:{''.join(chr(10) + l for l in lines)}\n\n"
        f"FINAL REMINDERS:\n" + ("\n".join(triggers) or "(none)")
    )


def judge_run(run: RunData, focus: str, *, model: str, api_key: str, timeout: float = 120.0) -> Dict[str, Any]:
    """Return {"score": int|None, "justification": str, "error": str|None}."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": _render(run, focus)}],
        # No temperature: current Claude models reject non-default sampling parameters.
    }
    try:
        response = httpx.post(OPENROUTER_URL, json=body, timeout=timeout,
                              headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        return {"score": None, "justification": "", "error": str(exc)}

    match = re.search(r"\{.*\}", content, re.S)
    try:
        parsed = json.loads(match.group(0) if match else content)
        score = int(parsed.get("score"))
        if not 1 <= score <= 5:
            raise ValueError(score)
        return {"score": score, "justification": str(parsed.get("justification", "")), "error": None}
    except Exception:
        return {"score": None, "justification": content[:500], "error": "unparseable judge output"}


def read_api_key(env_file: Optional[str]) -> Optional[str]:
    """Read OPENROUTER_API_KEY from the environment or a .env file."""
    import os

    if os.getenv("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    if env_file and os.path.exists(env_file):
        for line in open(env_file, encoding="utf-8"):
            key, _, value = line.strip().partition("=")
            if key.strip() == "OPENROUTER_API_KEY":
                return value.strip().strip("'\"")
    return None


__all__ = ["judge_run", "read_api_key"]
