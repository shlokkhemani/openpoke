"""Interaction agent helpers for prompt construction."""

from html import escape
from pathlib import Path
from typing import Dict, List

from ...services.execution import get_agent_roster

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()

# Budget ~4K tokens for conversation history in the user message.
# This is a safety cap — summarization should keep things smaller in practice.
_MAX_HISTORY_CHARS = 16_000

# Max active agents rendered individually before switching to summary mode.
_MAX_ACTIVE_RENDERED = 25


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
    sections.append(f"<active_agents>\n{_render_active_agents()}\n</active_agents>")
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    elif len(history) > _MAX_HISTORY_CHARS:
        # Truncate from the front (keep most recent), preserving line boundaries
        truncated = history[-_MAX_HISTORY_CHARS:]
        # Find the first complete XML tag boundary
        first_tag = truncated.find("<")
        if first_tag > 0:
            truncated = truncated[first_tag:]
        history = f"[earlier conversation truncated]\n{truncated}"
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Format currently active execution agents into XML tags for LLM awareness
def _render_active_agents() -> str:
    roster = get_agent_roster()
    roster.load()
    active = roster.get_active_agents()
    completed = roster.get_completed_agents()

    if not active and not completed:
        return "None"

    rendered: List[str] = []

    if len(active) <= _MAX_ACTIVE_RENDERED:
        # Under cap: render each individually
        for agent_name in active:
            name = escape(agent_name or "agent", quote=True)
            rendered.append(f'<agent name="{name}" status="active" />')
    else:
        # Over cap: show most recent N individually + summary count
        overflow = len(active) - _MAX_ACTIVE_RENDERED
        rendered.append(
            f'<active_summary count="{len(active)}" '
            f'showing="most_recent_{_MAX_ACTIVE_RENDERED}" '
            f'overflow="{overflow}" />'
        )
        for agent_name in active[-_MAX_ACTIVE_RENDERED:]:
            name = escape(agent_name or "agent", quote=True)
            rendered.append(f'<agent name="{name}" status="active" />')

    # Show recent completed agents compactly so the LLM can reuse them
    if completed:
        names = ", ".join(escape(n, quote=True) for n in completed[-10:])
        rendered.append(f'<completed_agents names="{names}" />')

    return "\n".join(rendered)


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
