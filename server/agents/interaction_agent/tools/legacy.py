"""Legacy (always-on) interaction-agent tools."""

from __future__ import annotations

import asyncio
from typing import Any

from ....config import get_settings
from ....logging_config import logger
from ....services.conversation import get_conversation_log
from ....services.execution import get_agent_roster, get_execution_agent_logs
from ...execution_agent.batch_manager import ExecutionBatchManager
from .types import ToolResult

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "send_message_to_agent",
            "description": "Deliver instructions to a specific execution agent. Creates a new agent if the name doesn't exist in the roster, or reuses an existing one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Human-readable agent name describing its purpose (e.g., 'Vercel Job Offer', 'Email to Sharanjeet'). This name will be used to identify and potentially reuse the agent."
                    },
                    "instructions": {"type": "string", "description": "Instructions for the agent to execute."},
                },
                "required": ["agent_name", "instructions"],
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


def get_execution_batch_manager() -> ExecutionBatchManager:
    """Return the manager used for worker dispatches.

    Keeping access behind functions lets evals replace the manager without
    relying on assignment through a re-exported module attribute.
    """
    return _EXECUTION_BATCH_MANAGER


def set_execution_batch_manager(manager: ExecutionBatchManager) -> None:
    """Replace the worker-dispatch manager (primarily for isolated evals)."""
    global _EXECUTION_BATCH_MANAGER
    _EXECUTION_BATCH_MANAGER = manager


def send_message_to_agent(agent_name: str, instructions: str) -> ToolResult:
    """Send instructions to an execution agent."""
    roster = get_agent_roster()
    roster.load()
    existing_agents = set(roster.get_agents())
    is_new = agent_name not in existing_agents

    if is_new:
        roster.add_agent(agent_name)

    get_execution_agent_logs().record_request(agent_name, instructions)
    if get_settings().budgeted_context:
        from ....services.execution.roster_v2 import get_roster_meta

        get_roster_meta().record_request(agent_name, instructions)

    action = "Created" if is_new else "Reused"
    logger.info(f"{action} agent: {agent_name}")

    async def _execute_async() -> None:
        try:
            result = await get_execution_batch_manager().execute_agent(agent_name, instructions)
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

    payload = {
        "status": "submitted",
        "agent_name": agent_name,
        "new_agent_created": is_new,
    }
    if get_settings().budgeted_context:
        payload["note"] = (
            "The worker is running in the background and has NOT finished. Its result will arrive later as a "
            "separate agent message. Do not tell the user the task is done or sent; at most say what is in progress."
        )
    return ToolResult(success=True, payload=payload)


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


def send_draft(to: str, subject: str, body: str) -> ToolResult:
    """Record a draft update in the conversation log for the interaction agent."""
    log = get_conversation_log()
    message = f"To: {to}\nSubject: {subject}\n\n{body}"
    log.record_reply(message)
    logger.info(f"Draft recorded for: {to}")
    return ToolResult(
        success=True,
        payload={"status": "draft_recorded", "to": to, "subject": subject},
        recorded_reply=True,
    )


def wait(reason: str) -> ToolResult:
    """Wait silently and add a wait log entry that is not visible to the user."""
    log = get_conversation_log()
    log.record_wait(reason)
    return ToolResult(
        success=True,
        payload={"status": "waiting", "reason": reason},
        recorded_reply=True,
    )


__all__ = [
    "TOOL_SCHEMAS",
    "get_execution_batch_manager",
    "send_draft",
    "send_message_to_agent",
    "send_message_to_user",
    "set_execution_batch_manager",
    "wait",
]
