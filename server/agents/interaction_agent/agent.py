"""Interaction agent helpers for prompt construction."""

from html import escape
from pathlib import Path
from typing import Dict, List

from ...services.execution import get_agent_roster
from ...services.user_profile import get_user_profile
from ..execution_agent.tools.registry import get_tool_schemas

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()


def _generate_available_tools_section() -> str:
    """
    Generate a formatted section listing all available tools grouped by category.
    
    Returns:
        Markdown-formatted string with categorized tool listings
    """
    tool_schemas = get_tool_schemas()
    
    # Group tools by category
    categories: Dict[str, List[str]] = {
        "Gmail": [],
        "Google Calendar": [],
        "Google Super": [],
        "Search": [],
        "Triggers": [],
        "Tasks": [],
    }
    
    for schema in tool_schemas:
        func = schema.get("function", {})
        name = func.get("name", "")
        description = func.get("description", "")
        
        if name.startswith("gmail_"):
            categories["Gmail"].append(f"- **{name}**: {description}")
        elif name.startswith("calendar_"):
            categories["Google Calendar"].append(f"- **{name}**: {description}")
        elif name.startswith("googlesuper_"):
            categories["Google Super"].append(f"- **{name}**: {description}")
        elif name.startswith("search_") or name.startswith("exa_"):
            categories["Search"].append(f"- **{name}**: {description}")
        elif name.startswith("trigger_"):
            categories["Triggers"].append(f"- **{name}**: {description}")
        elif name.startswith("task_"):
            categories["Tasks"].append(f"- **{name}**: {description}")
    
    # Build the formatted output
    lines = ["# AVAILABLE TOOLS", ""]
    lines.append("Your execution agents have access to the following tools. When a user asks what you can do or what tools are available, reference these capabilities:")
    lines.append("")
    
    for category, tools in categories.items():
        if tools:
            lines.append(f"## {category}")
            lines.append("")
            lines.extend(tools)
            lines.append("")
    
    return "\n".join(lines)


# Load and return the pre-defined system prompt from markdown file with user profile
def build_system_prompt() -> str:
    """Return the system prompt for the interaction agent with user profile information."""
    from ...services.lessons_learned import get_lessons_service
    from ...services.user_memory import get_user_memory_service

    profile_store = get_user_profile()
    profile = profile_store.load()

    # Start with base prompt
    sections = [SYSTEM_PROMPT]

    # Add available tools section
    sections.append(_generate_available_tools_section())

    # Add lessons learned section (critical - shows past mistakes)
    lessons_service = get_lessons_service()
    lessons_text = lessons_service.format_lessons_for_prompt(max_lessons=5)
    if lessons_text:
        sections.append(lessons_text)

    # Add user memories section (contextual information about the user)
    memory_service = get_user_memory_service()
    memories_text = memory_service.format_memories_for_prompt(max_memories=5)
    if memories_text:
        sections.append(memories_text)

    # Add user profile section
    user_context = []
    if profile.get("userName"):
        user_context.append(f"- User's name: {profile['userName']}")
    if profile.get("birthDate"):
        user_context.append(f"- User's date of birth: {profile['birthDate']}")
    if profile.get("location"):
        user_context.append(f"- User's location: {profile['location']}")

    if user_context:
        profile_section = "\n\n# USER PROFILE\n\nYou have access to the following information about the user:\n\n" + "\n".join(user_context) + "\n\nUse this information to personalize your responses when relevant. Remember these details naturally without explicitly mentioning you have this information unless necessary."
        sections.append(profile_section)
    else:
        # When no profile exists, guide user to add their info
        no_profile_section = "\n\n# USER PROFILE\n\n⚠️ **NO USER PROFILE DATA AVAILABLE**\n\nThe user hasn't added their profile information yet.\n\n**When the user asks what you know about them:**\n- Tell them you don't have any info yet\n- Direct them to add their profile at: https://alyn.up.railway.app/\n- Explain that adding their info (name, date of birth, location) helps you personalize responses\n\nExample response: \"Je n'ai pas encore d'infos sur toi. Tu peux ajouter ton profil (nom, date de naissance, localisation) sur https://alyn.up.railway.app/ pour que je personnalise mes réponses.\""
        sections.append(no_profile_section)

    return "\n\n".join(sections)


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
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Format currently active execution agents into XML tags for LLM awareness
def _render_active_agents() -> str:
    roster = get_agent_roster()
    roster.load()
    agents = roster.get_agents()

    if not agents:
        return "None"

    rendered: List[str] = []
    for agent_name in agents:
        name = escape(agent_name or "agent", quote=True)
        rendered.append(f'<agent name="{name}" />')

    return "\n".join(rendered)


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
