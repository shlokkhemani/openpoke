"""Interaction agent helpers for prompt construction."""

from html import escape
from pathlib import Path
from typing import Dict, List

from ...config import get_settings
from ...services.execution import get_agent_roster

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()

BUDGETED_CONTEXT_ADDENDUM = """
Context Window Management

- The conversation history is kept within a token budget. Recent entries appear in full; older ones appear only as one-line index entries inside <older_entries>, and very large entries appear as a head/tail preview marked truncated="true".
- Every entry carries an id. When you need something you cannot see verbatim (a draft body, a thread or draft id, an exact rule, pasted content), call `recall_history` with the entry ids (preferred, from the index) or a short search query of distinctive words or identifiers, then act on what it returns in the same turn. Never guess or reconstruct ids and exact text from memory.
- A recall is a lookup, not a checkpoint: it does not change what the user asked for. If the user already gave an instruction or confirmation, carry it out after the recall; do not ask again.
- If the relevant details are already visible inline (including an earlier reply that already summarized an entry) or in <conversation_summary>, do not recall or digest; act directly.
- A very long incoming message (a pasted document, a merged batch of worker results) is shown as a head/tail preview with its entry id.
DIGEST_BULLET_PLACEHOLDER

Email Is Always Done By A Worker

- You cannot compose, create or send email. `send_draft` only displays a draft that a worker has already created and reported (with its draft id). For any request to email, reply, forward or send: dispatch a worker to create the draft, wait for its message, then show that draft and ask for confirmation. When the user confirms, dispatch the worker to send that draft id.

ROSTER_BULLET_PLACEHOLDER

Look Before You Dispatch

- Before dispatching a worker to look something up, check whether the content is already in the conversation: inline, previewed (an entry marked truncated="true" with an id), in <conversation_summary>, or listed in <older_entries>. A worker report that says a document or thread "follows" IS that document: it is in the conversation, not in email. Read it here: digest_entry for synthesis, recall_history for an exact passage. Dispatch a worker only when the information must come from email or an action must be taken (create, send, forward). Sending a worker to "search" for something that is already an entry in this conversation is wrong and wastes the turn.

Turn Discipline

- Calling `wait` ends your turn. Use it only when there is truly nothing to say; you will be invoked again when a worker reports back. Never call `wait` twice in one turn.
- Dispatch each worker at most once per turn. After you have acknowledged the user and dispatched, stop; do not poll the worker or dispatch it again to ask for status. Its result arrives as a new agent message.
- Do not tell the user something is sent or done until a worker message confirms it.
- When the user confirms sending ("send it", "go ahead", "looks good"), dispatch the send in that same turn. Do not ask follow-up questions about wording, sign-offs or placeholders at that point; the user has already approved the draft they saw.
""".strip()


# Load and return the pre-defined system prompt from markdown file
ROSTER_BULLET = """Choosing A Worker

- <active_agents> lists only the most recently used workers, with purpose, last use and identifiers they hold; <more_agents> gives the count of older ones. Before creating a new worker, call `find_worker` with a few words about the task or counterpart; reuse the match that did related work, especially one holding the draft or thread id you need. Names can look alike: match on purpose and identifiers, not on the name. A listed worker with no ids and a generic purpose has not done the work you need; when the task depends on something a worker did earlier (a draft it created, a thread it found), call find_worker first even if a similar name is listed.
- Name a new worker as topic plus counterpart, e.g. "Contract - Sarah Kim (Acme)", so it can be found later."""

DIGEST_BULLET = """- Two ways to use a large entry, pick by what the task needs:
  - Synthesis (summarize it, extract terms or figures, answer a question about it): call `digest_entry(entry_ids, question)`. It reads the whole entries outside your context and returns a compact answer; several ids in one call are digested separately and combined. Ask for everything you need in one call. Never page through a large entry with recall_history to read all of it; that will not fit (recall is limited to a few calls per turn).
  - Verbatim (text that must be sent or shown exactly): do not digest and do not read it. Pass it by reference: tell the worker "use conversation entry N as the body" and it builds the draft from that entry server-side. When a worker reports a draft id, show it with `send_draft_v2(draft_id, to, subject, body_preview)`; the body stays in Gmail and is sent by id."""


def build_system_prompt() -> str:
    """Return the system prompt for the interaction agent."""
    settings = get_settings()
    if settings.budgeted_context:
        addendum = BUDGETED_CONTEXT_ADDENDUM.replace(
            "DIGEST_BULLET_PLACEHOLDER", DIGEST_BULLET if settings.interaction_digest_enabled else "").replace(
            "ROSTER_BULLET_PLACEHOLDER", ROSTER_BULLET if settings.roster_v2_enabled else "")
        return f"{SYSTEM_PROMPT}\n\n{addendum}"
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
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Format currently active execution agents into XML tags for LLM awareness
def _render_active_agents() -> str:
    settings = get_settings()
    if settings.budgeted_context and settings.roster_v2_enabled:
        from ...services.execution.roster_v2 import get_roster_meta

        return get_roster_meta().render(inline_limit=settings.roster_inline_limit)
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
