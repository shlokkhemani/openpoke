"""Interaction agent helpers for prompt construction."""

from html import escape
from pathlib import Path
from typing import Dict, List

from ...services.execution import get_agent_roster

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()


# Load and return the pre-defined system prompt from markdown file
def build_system_prompt() -> str:
    """Return the static system prompt for the interaction agent."""
    return SYSTEM_PROMPT


# Build structured message with conversation history, focused agents, and current turn
def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    message_type: str = "user",
) -> List[Dict[str, str]]:
    """Compose a message that bundles history, relevant agents, and the latest turn."""
    sections: List[str] = []

    sections.append(_render_conversation_history(transcript))
    sections.append(
        f"<active_agents>\n{_render_active_agents(latest_text, transcript)}\n</active_agents>"
    )
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Format the agents most relevant to this turn into XML tags for the LLM
def _render_active_agents(latest_text: str = "", transcript: str = "") -> str:
    roster = get_agent_roster()
    roster.load()
    agents = roster.select_for_prompt(latest_text, transcript)

    if not agents:
        return "None"

    rendered: List[str] = []
    for record in agents:
        name = escape(record.name or "agent", quote=True)
        hint = _escape_attribute(record.last_instructions)
        if hint:
            rendered.append(f'<agent name="{name}" last_request="{hint}" />')
        else:
            rendered.append(f'<agent name="{name}" />')

    return "\n".join(rendered)


# Escape text for safe use inside a single XML attribute
def _escape_attribute(value: str) -> str:
    if not value:
        return ""
    return escape(" ".join(value.split()), quote=True)


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
