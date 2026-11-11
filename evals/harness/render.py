"""Render case history and rosters exactly as the production Interaction Agent sees them."""
from __future__ import annotations

from datetime import timedelta
from html import escape

from evals.clock import EVAL_NOW
from evals.grading import EVAL_MODES, NAME_DISPATCH_MODES
from evals.schema import AgentDef, Turn

_TAGS = {"user": "user_message", "assistant": "poke_reply", "agent": "agent_message"}
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"  # ConversationLog._append


def _payload(turn: Turn, mode: str) -> str:
    if turn.role != "agent":
        return turn.text
    if mode in NAME_DISPATCH_MODES:
        return f"[SUCCESS] {turn.agent_name}: {turn.text}"
    return f"[SUCCESS] {turn.agent_name} (agent_id={turn.agent_id}): {turn.text}"


def render_transcript(history: list[Turn], mode: str) -> str:
    """Same output as ``ConversationLog.load_transcript``.

    Timestamps are deterministic: turns are one minute apart and the last one is one minute
    before ``EVAL_NOW``.
    """
    if mode not in EVAL_MODES:
        raise ValueError(f"unknown roster mode {mode!r}")
    parts: list[str] = []
    for i, turn in enumerate(history):
        tag = _TAGS[turn.role]
        ts = (EVAL_NOW - timedelta(minutes=len(history) - i)).strftime(_TIMESTAMP_FORMAT)
        parts.append(f'<{tag} timestamp="{ts}">{escape(_payload(turn, mode), quote=False)}</{tag}>')
    return "\n".join(parts)


def render_legacy_roster(roster: list[AgentDef]) -> str:
    """The names-only roster of the legacy modes."""
    if not roster:
        return "None"
    return "\n".join(f'<agent name="{escape(a.name or "agent", quote=True)}" />' for a in roster)
