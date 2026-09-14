from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import Dict, List

from .state import LogEntry


@dataclass(frozen=True)
class SummaryPrompt:
    system_prompt: str
    messages: List[Dict[str, str]]


_SYSTEM_PROMPT = dedent(
    """
    You are the assistant's chief-of-staff memory curator. Produce a complete working-memory briefing
    that the assistant reads before every response. Follow these directives without exception:

    FORMAT — Always output using this exact structure (replace angle brackets with content):

    Summary generated: <latest relevant timestamp from the logs in YYYY-MM-DD HH:MM> (user timezone)

    Timeline & Commitments:
    - <YYYY-MM-DD HH:MM> — <event / meeting / travel>. Include participants, location, objective,
      required deliverables, and current status (confirmed / pending / awaiting response) in chronological order.

    Pending & Follow-ups:
    - <Due YYYY-MM-DD HH:MM or window> — <open task>. Specify owner, status, next step, blockers,
      and any tracking IDs, links, budgets, or artefacts mentioned.

    Routines & Recurring:
    - <Cadence (e.g., Mon/Wed/Fri 07:00)> — <habit, reminder, or standing order>. Note fulfilment channel,
      lead times, budgets, or escalation rules if provided.

    Preferences & Profile:
    - <Stable preference, constraint, or personal detail>. Capture formats, brands, dietary needs,
      communication styles, scheduling windows, or other personalization cues.

    Context & Notes:
    - <Strategic insight, dependency, risk, metric, or configuration> that informs future decisions and
      does not belong in earlier sections.

    If a section has no content, output a single bullet "- No items."

    RULES — Obey all of these simultaneously:
    1. Rebuild the entire briefing from scratch on every run; never append or partially edit prior text.
    2. Merge new actionable information while retaining still-relevant facts from the previous summary.
    3. Remove items that are complete or obsolete unless the logs explicitly keep them active.
    4. Convert every relative time phrase (today, tomorrow, next week, tonight, etc.) into explicit
       YYYY-MM-DD (and HH:MM when known) timestamps in the user's timezone.
    5. Include all salient details for people, locations, deliverables, tools, identifiers, budgets, and links
       whenever they appear in the logs.
    6. Order bullets earliest-first within each section and keep language concise yet information-dense.
    7. Do not invent facts; only use information present in the existing summary or new logs.
    """
).strip()


def _format_existing_summary(previous_summary: str) -> str:
    summary = (previous_summary or "").strip()
    return summary if summary else "None"


def _bound(payload: str, max_tokens: int) -> str:
    """Head/tail preview for oversized entries so one entry cannot blow up the summariser prompt."""
    if max_tokens <= 0:
        return payload
    max_chars = max_tokens * 4
    if len(payload) <= max_chars:
        return payload
    head = int(max_chars * 0.7)
    tail = max_chars - head
    return f"{payload[:head]}\n[... {len(payload) - head - tail:,} characters omitted ...]\n{payload[-tail:]}"


def _format_log_entries(entries: List[LogEntry], entry_max_tokens: int = 0) -> str:
    lines: List[str] = []
    for entry in entries:
        label = entry.tag.replace("_", " ")
        payload = _bound(entry.payload.strip(), entry_max_tokens)
        index = entry.index if entry.index >= 0 else "?"
        if payload:
            lines.append(f"[{index}] {label}: {payload}")
        else:
            lines.append(f"[{index}] {label}: (empty)")
    return "\n".join(lines) if lines else "(no new logs)"


def build_summarization_prompt(
    previous_summary: str, entries: List[LogEntry], entry_max_tokens: int = 0
) -> SummaryPrompt:
    content = dedent(
        f"""
        Existing memory summary:
        {_format_existing_summary(previous_summary)}

        New conversation logs to merge:
        {_format_log_entries(entries, entry_max_tokens)}
        """
    ).strip()

    messages = [{"role": "user", "content": content}]
    return SummaryPrompt(system_prompt=_SYSTEM_PROMPT, messages=messages)


__all__ = ["SummaryPrompt", "build_summarization_prompt"]
