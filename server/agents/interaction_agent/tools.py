"""Tool definitions for interaction agent."""

import asyncio
import contextvars
import json
from dataclasses import dataclass
from typing import Any, Optional

from ...logging_config import logger
from ...services.conversation import get_conversation_log
from ...services.execution import get_agent_roster
from ...utils.timezones import now_in_user_timezone
from ..execution_agent.batch_manager import ExecutionBatchManager


@dataclass
class ToolResult:
    """Standardized payload returned by interaction-agent tools."""

    success: bool
    payload: Any = None
    user_message: Optional[str] = None
    recorded_reply: bool = False

# Tool schemas for OpenRouter
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "delegate",
            "description": (
                "Hand the user's latest request to an execution agent. You do NOT write instructions: the agent "
                "automatically receives the user's latest message verbatim and your previous reply. Reuse the agent "
                "that owns the task for follow-ups; pass a new goal-based name to start a new task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Goal-based task name, e.g. 'Team offsite planning' or 'Insurance quotes'. An existing name reuses that agent.",
                    },
                    "task": {
                        "type": "string",
                        "description": (
                            "The part of the request this agent should do, in a few words. Required when the user's "
                            "message contains several unrelated tasks (one delegate per task), and when you act on an "
                            "agent result rather than a new user message. Omit it when the whole message is one task."
                        ),
                    },
                    "note": {
                        "type": "string",
                        "description": (
                            "Optional, a few words. Only for context the agent can't see in the latest message, e.g. "
                            "a constraint the user mentioned earlier."
                        ),
                    },
                },
                "required": ["agent_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_agents",
            "description": "Search existing tasks (execution agents) by keywords and status. Call it before delegating, to find the agent that already owns a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords, names or emails. Only matching agents are returned. Omit to list the most recently active agents."},
                    "status": {
                        "type": "string",
                        "enum": ["active", "closed", "all"],
                        "description": "active = not finished, closed = done or archived, all = both (default).",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 3)."},
                    "offset": {"type": "integer", "description": "Skip this many results, for paging."},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message_to_user",
            "description": "Deliver a natural-language response directly to the user. Use this for updates, confirmations, or any assistant response the user should see immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Plain-text message that will be shown to the user and recorded in the conversation log.",
                    },
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_draft",
            "description": "Record an email draft so the user can review the exact text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email for the draft.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject for the draft.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body content (plain text).",
                    },
                },
                "required": ["to", "subject", "body"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait silently when a message is already in conversation history to avoid duplicating responses. Adds a <wait> log entry that is not visible to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of why waiting (e.g., 'Message already sent', 'Draft already created').",
                    },
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]

_EXECUTION_BATCH_MANAGER = ExecutionBatchManager()

# Set by the interaction runtime for each turn: "user" (a new user message) or "agent" (an agent result).
CURRENT_TURN_TYPE: contextvars.ContextVar[str] = contextvars.ContextVar("current_turn_type", default="user")


def build_handoff(note: Optional[str] = None, task: Optional[str] = None) -> str:
    """Build the execution agent's input from the conversation log (no LLM-written instructions)."""
    from html import escape

    entries = list(get_conversation_log().iter_entries())
    latest_user_index = max((i for i, (tag, _, _) in enumerate(entries) if tag == "user_message"), default=None)

    sections = []
    if latest_user_index is not None:
        previous_reply = next(
            (payload for tag, _, payload in reversed(entries[:latest_user_index]) if tag == "poke_reply"),
            None,
        )
        if previous_reply:
            sections.append(f"<previous_poke_reply>\n{escape(previous_reply, quote=False)}\n</previous_poke_reply>")
        tag = "background_user_message" if task and task.strip() else "user_message"
        sections.append(f"<{tag}>\n{escape(entries[latest_user_index][2], quote=False)}\n</{tag}>")
    if note and note.strip():
        sections.append(f"<note>\n{escape(note.strip(), quote=False)}\n</note>")
    if task and task.strip():
        # The assigned part comes first; the user's message is only background for it.
        sections.insert(0, f"<task>\n{escape(task.strip(), quote=False)}\n</task>")
    if not sections:
        sections.append("<note>\n(no request available)\n</note>")
    # The agent no longer gets Poke-written instructions, so give it the date/time Poke would have seen.
    sections.insert(0, f"<current_time>{now_in_user_timezone('%A %Y-%m-%d %H:%M %Z')}</current_time>")
    return "\n\n".join(sections)


# Create, reuse or revive an execution agent and dispatch the verbatim request asynchronously
def delegate(agent_name: str, note: Optional[str] = None, task: Optional[str] = None) -> ToolResult:
    """Hand the latest user request (or the given part of it) to an execution agent."""
    from ...services.execution.lifecycle import revive

    if CURRENT_TURN_TYPE.get() == "agent" and not (task and task.strip()):
        return ToolResult(
            success=False,
            payload={"error": "On an agent-result turn, give `task`: say exactly what this agent should do. "
                              "The user's latest message is not a new request here."},
        )

    roster = get_agent_roster()
    is_new = roster.get_record(agent_name) is None
    revived = False
    if is_new:
        roster.add_agent(agent_name)
    else:
        revived = revive(agent_name)

    handoff = build_handoff(note, task)
    action = "Created" if is_new else ("Revived" if revived else "Reused")
    logger.info(f"{action} agent: {agent_name}")

    async def _execute_async() -> None:
        try:
            result = await _EXECUTION_BATCH_MANAGER.execute_agent(agent_name, handoff)
            status = "SUCCESS" if result.success else "FAILED"
            logger.info(f"Agent '{agent_name}' completed: {status}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Agent '{agent_name}' failed: {str(exc)}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("No running event loop available for async execution")
        return ToolResult(success=False, payload={"error": "No event loop available"})

    loop.create_task(_execute_async())

    return ToolResult(
        success=True,
        payload={
            "status": "submitted",
            "agent_name": agent_name,
            "new_agent_created": is_new,
            "revived": revived,
        },
    )


def find_agents_tool(
    query: Optional[str] = None,
    status: str = "all",
    limit: int = 3,
    offset: int = 0,
) -> ToolResult:
    """Search the roster."""
    from ...services.execution.agent_search import find_agents, render_agent

    if status not in ("active", "closed", "all"):
        return ToolResult(success=False, payload={"error": "status must be active, closed or all"})
    records = find_agents(query=query, status=status, limit=limit, offset=offset)  # type: ignore[arg-type]
    return ToolResult(success=True, payload={"agents": [render_agent(r) for r in records]})


# Send immediate message to user and record in conversation history
def send_message_to_user(message: str) -> ToolResult:
    """Record a user-visible reply in the conversation log."""
    log = get_conversation_log()
    log.record_reply(message)

    return ToolResult(
        success=True,
        payload={"status": "delivered"},
        user_message=message,
        recorded_reply=True,
    )


# Format and record email draft for user review
def send_draft(
    to: str,
    subject: str,
    body: str,
) -> ToolResult:
    """Record a draft update in the conversation log for the interaction agent."""
    log = get_conversation_log()

    message = f"To: {to}\nSubject: {subject}\n\n{body}"

    log.record_reply(message)
    logger.info(f"Draft recorded for: {to}")

    return ToolResult(
        success=True,
        payload={
            "status": "draft_recorded",
            "to": to,
            "subject": subject,
        },
        recorded_reply=True,
    )


# Record silent wait state to avoid duplicate responses
def wait(reason: str) -> ToolResult:
    """Wait silently and add a wait log entry that is not visible to the user."""
    log = get_conversation_log()
    
    # Record a dedicated wait entry so the UI knows to ignore it
    log.record_wait(reason)
    

    return ToolResult(
        success=True,
        payload={
            "status": "waiting",
            "reason": reason,
        },
        recorded_reply=True,
    )


# Return predefined tool schemas for LLM function calling
def get_tool_schemas():
    """Return OpenAI-compatible tool schemas."""
    return TOOL_SCHEMAS


# Route tool calls to appropriate handlers with argument validation and error handling
def handle_tool_call(name: str, arguments: Any) -> ToolResult:
    """Handle tool calls from interaction agent."""
    try:
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        elif isinstance(arguments, dict):
            args = arguments
        else:
            return ToolResult(success=False, payload={"error": "Invalid arguments format"})

        if name == "delegate":
            return delegate(**args)
        if name == "find_agents":
            return find_agents_tool(**args)
        if name == "send_message_to_user":
            return send_message_to_user(**args)
        if name == "send_draft":
            return send_draft(**args)
        if name == "wait":
            return wait(**args)

        logger.warning("unexpected tool", extra={"tool": name})
        return ToolResult(success=False, payload={"error": f"Unknown tool: {name}"})
    except json.JSONDecodeError:
        return ToolResult(success=False, payload={"error": "Invalid JSON"})
    except TypeError as exc:
        return ToolResult(success=False, payload={"error": f"Missing required arguments: {exc}"})
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("tool call failed", extra={"tool": name, "error": str(exc)})
        return ToolResult(success=False, payload={"error": "Failed to execute"})
