"""Interaction agent helpers for prompt construction."""

from pathlib import Path
from typing import Dict, List, Literal, Optional

_PROMPT_DIR = Path(__file__).parent
# The shared prompt holds this line where the tool-interface-specific routing rules go.
_TOOL_RULES_PLACEHOLDER = "{{TOOL_RULES}}"
_TOOL_BLOCK_FILES = {
    "names": ("prompt_tools_names.md",),
    "ids": ("prompt_tools_ids.md",),
    "hybrid": ("prompt_tools_ids.md", "prompt_tools_hybrid.md"),  # ids block + search addendum
}

ToolStyle = Literal["names", "ids", "hybrid"]


def _read(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def _compose(tool_style: ToolStyle) -> str:
    shared = _read("system_prompt.md")
    if shared.count(_TOOL_RULES_PLACEHOLDER) != 1:
        raise RuntimeError("system_prompt.md must contain the tool rules placeholder exactly once")
    block = "\n".join(_read(name).strip() for name in _TOOL_BLOCK_FILES[tool_style])
    return shared.replace(_TOOL_RULES_PLACEHOLDER, block).strip()


_SYSTEM_PROMPTS: Dict[str, str] = {style: _compose(style) for style in _TOOL_BLOCK_FILES}


# Compose the system prompt: shared text plus the routing rules for one tool interface
def build_system_prompt(tool_style: ToolStyle = "ids") -> str:
    """Return the IA system prompt for the ``agent_id``/``name`` tool ("ids", production ``full``), the
    same plus the ``search_agents`` addendum ("hybrid", production ``hybrid``), or the legacy
    ``agent_name`` tool ("names", eval-only ``legacy_rules``)."""
    try:
        return _SYSTEM_PROMPTS[tool_style]
    except KeyError:
        raise ValueError(f"unknown tool style {tool_style!r}") from None


# Build structured message with conversation history, active agents, and current turn
def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    message_type: str = "user",
    roster_block: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Compose a message that bundles history, roster, and the latest turn.

    ``roster_block`` is the body of ``<active_agents>``; None renders "None".
    """
    sections: List[str] = []
    if roster_block is None:
        roster_block = "None"

    sections.append(_render_conversation_history(transcript))
    sections.append(f"<active_agents>\n{roster_block}\n</active_agents>")
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
