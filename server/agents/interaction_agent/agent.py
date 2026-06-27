"""Interaction agent helpers for prompt construction."""

import re
from html import escape
from pathlib import Path
from typing import Dict, List, Set

from ...services.execution import get_agent_roster

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()

# Budget ~4K tokens for conversation history in the user message.
_MAX_HISTORY_CHARS = 16_000

# Max active agents rendered individually before switching to summary mode.
_MAX_ACTIVE_RENDERED = 25

# Words to ignore when scoring relevance
_STOP_WORDS: Set[str] = {
    "the", "a", "an", "to", "for", "of", "in", "on", "and", "is", "it",
    "my", "me", "i", "do", "can", "this", "that", "with", "from", "agent",
    "please", "what", "how", "about", "exec", "execution",
}


def _tokenize(text: str) -> Set[str]:
    """Extract lowercase word tokens from text, filtering stop words."""
    words = set(re.findall(r"[a-z]+", text.lower()))
    return words - _STOP_WORDS


def _stem(word: str) -> str:
    """Minimal suffix stripping for matching (emails→email, booking→book)."""
    for suffix in ("ing", "tion", "ment", "ness", "able", "ible", "ies", "es", "ed", "ly", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _relevance_score(agent_name: str, query_tokens: Set[str]) -> int:
    """Score an agent name by keyword overlap with the query (with stemming)."""
    agent_tokens = _tokenize(agent_name)
    query_stems = {_stem(w) for w in query_tokens}
    agent_stems = {_stem(w) for w in agent_tokens}
    # Exact match counts 2, stem match counts 1
    exact = len(agent_tokens & query_tokens)
    stem_only = len(agent_stems & query_stems) - exact
    return exact * 2 + max(stem_only, 0)


# Load and return the pre-defined system prompt from markdown file
def build_system_prompt() -> str:
    """Return the static system prompt for the interaction agent."""
    return SYSTEM_PROMPT


# Build structured message with conversation history, active agents, and current turn
def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    message_type: str = "user",
) -> List[Dict[str, str]]:
    """Compose a message that bundles history, roster, and the latest turn."""
    sections: List[str] = []

    sections.append(_render_conversation_history(transcript))
    sections.append(
        f"<active_agents>\n{_render_active_agents(latest_text)}\n</active_agents>"
    )
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    elif len(history) > _MAX_HISTORY_CHARS:
        truncated = history[-_MAX_HISTORY_CHARS:]
        first_tag = truncated.find("<")
        if first_tag > 0:
            truncated = truncated[first_tag:]
        history = f"[earlier conversation truncated]\n{truncated}"
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Format currently active execution agents into XML tags for LLM awareness
def _render_active_agents(query: str = "") -> str:
    roster = get_agent_roster()
    roster.load()
    active = roster.get_active_agents()
    completed = roster.get_completed_agents()

    if not active and not completed:
        return "None"

    rendered: List[str] = []

    if len(active) <= _MAX_ACTIVE_RENDERED:
        for agent_name in active:
            name = escape(agent_name or "agent", quote=True)
            rendered.append(f'<agent name="{name}" status="active" />')
    else:
        # Over cap: select by relevance to current query, fallback to recency
        selected = _select_relevant_agents(active, query, _MAX_ACTIVE_RENDERED)
        overflow = len(active) - len(selected)
        rendered.append(
            f'<active_summary count="{len(active)}" '
            f'showing="{len(selected)}" '
            f'overflow="{overflow}" '
            f'selection="relevance+recency" />'
        )
        # Cluster selected agents for compact rendering
        rendered.extend(_cluster_agents(selected))

    # Show recent completed agents compactly so the LLM can reuse them
    if completed:
        names = ", ".join(escape(n, quote=True) for n in completed[-10:])
        rendered.append(f'<completed_agents names="{names}" />')

    return "\n".join(rendered)


def _select_relevant_agents(
    active: List[str], query: str, limit: int
) -> List[str]:
    """Select up to `limit` agents by relevance to query, with recency tiebreak.

    Strategy: score each agent by keyword overlap with the query.
    Take top scorers first, then fill remaining slots with most recent agents.
    This ensures relevant agents are always visible, while recent agents
    provide fallback context.
    """
    query_tokens = _tokenize(query)

    if not query_tokens:
        # No usable query — fall back to most recent
        return active[-limit:]

    # Score all agents
    scored = [(name, _relevance_score(name, query_tokens)) for name in active]

    # Split into relevant (score > 0) and non-relevant
    relevant = [(name, score) for name, score in scored if score > 0]
    relevant.sort(key=lambda x: x[1], reverse=True)

    # Take top relevant agents (up to half the budget)
    relevance_budget = limit // 2
    selected_relevant = [name for name, _ in relevant[:relevance_budget]]

    # Fill remaining slots with most recent agents (excluding already selected)
    selected_set = set(selected_relevant)
    remaining_slots = limit - len(selected_relevant)
    recent_fill = [n for n in reversed(active) if n not in selected_set][:remaining_slots]

    # Combine: relevant first, then recent
    return selected_relevant + recent_fill


def _cluster_agents(agents: List[str]) -> List[str]:
    """Cluster agents with shared leading word into compact group tags.

    Groups of 3+ agents sharing the same first word are collapsed into
    a single <agent_group> tag. Singletons and pairs remain individual.
    """
    from collections import defaultdict

    # Group by first word
    groups: Dict[str, List[str]] = defaultdict(list)
    for name in agents:
        first_word = name.split()[0].lower() if name.split() else ""
        groups[first_word].append(name)

    rendered: List[str] = []
    rendered_set: Set[str] = set()

    for prefix, members in groups.items():
        if len(members) >= 3:
            # Cluster: show as group
            suffixes = []
            for m in members:
                # Strip the prefix word to get the distinguishing part
                parts = m.split(maxsplit=1)
                suffix = parts[1] if len(parts) > 1 else m
                suffixes.append(escape(suffix, quote=True))
            rendered.append(
                f'<agent_group prefix="{escape(prefix.title(), quote=True)}" '
                f'count="{len(members)}" '
                f'agents="{"; ".join(suffixes)}" />'
            )
            rendered_set.update(members)

    # Remaining agents rendered individually
    for name in agents:
        if name not in rendered_set:
            rendered.append(f'<agent name="{escape(name, quote=True)}" status="active" />')

    return rendered


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
