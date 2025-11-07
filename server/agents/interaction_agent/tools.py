"""Tool definitions for interaction agent."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ...logging_config import logger
from ...services.conversation import get_conversation_log
from ...services.execution import get_agent_roster, get_execution_agent_logs
## Suppression de l'import iMessage : get_message_context, send_imessage
from ...utils.tool_validation import get_interaction_tool_names
from ..execution_agent.batch_manager import ExecutionBatchManager


@dataclass
class ToolResult:
    """Standardized payload returned by interaction-agent tools."""

    success: bool
    payload: Any = None
    user_message: Optional[str] = None
    recorded_reply: bool = False

_KNOWN_TOOL_NAMES = get_interaction_tool_names()

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
    {
        "type": "function",
        "function": {
            "name": "remove_agent",
            "description": "Remove an execution agent from the roster when it is no longer needed or is a duplicate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Exact name of the agent to remove (case-insensitive).",
                    },
                    "clear_logs": {
                        "type": "boolean",
                        "description": "Optional flag to delete the agent's execution logs as well.",
                        "default": False,
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
            "name": "add_lesson",
            "description": "Add a new lesson learned to the PostgreSQL database. Use this when the user explicitly asks you to remember something, learn from a mistake, or add a lesson for future reference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category of the lesson (e.g., 'email', 'calendar', 'communication', 'user_preference', 'tool_usage')",
                    },
                    "problem": {
                        "type": "string",
                        "description": "Description of the problem, mistake, or situation that occurred",
                    },
                    "solution": {
                        "type": "string",
                        "description": "How to avoid or fix this problem in the future, or what to do in similar situations",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context about when/why this lesson is important",
                    },
                },
                "required": ["category", "problem", "solution"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lessons",
            "description": "Retrieve lessons learned from the PostgreSQL database. Use this when the user asks to see lessons, list what you've learned, or show past mistakes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Optional: Filter lessons by category (e.g., 'email', 'calendar'). If not provided, returns all lessons.",
                    },
                    "min_occurrences": {
                        "type": "integer",
                        "description": "Optional: Minimum number of occurrences to filter by. Defaults to 1 (all lessons).",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_lesson",
            "description": "Delete a specific lesson from the PostgreSQL database by its ID. Use this when the user explicitly asks to remove or delete a lesson.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lesson_id": {
                        "type": "integer",
                        "description": "The ID of the lesson to delete (from the lessons_learned table)",
                    },
                },
                "required": ["lesson_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_memory",
            "description": "Add or update contextual information about the user (Mem0-like memory). Use this when the user shares important facts about themselves, their relationships, preferences, work, habits, or ongoing projects.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category: 'relationship', 'preference', 'work', 'habit', or 'project'",
                    },
                    "key": {
                        "type": "string",
                        "description": "Unique identifier (e.g., 'colleague_theo', 'communication_style')",
                    },
                    "value": {
                        "type": "string",
                        "description": "The memory content (e.g., 'Théo is a colleague', 'prefers concise responses')",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional additional context about when/why this is important",
                    },
                },
                "required": ["category", "key", "value"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_memories",
            "description": "Retrieve contextual memories about the user from PostgreSQL. Use this when the user asks what you know about them, their relationships, preferences, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Optional: Filter by category ('relationship', 'preference', 'work', 'habit', 'project')",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "Delete a specific memory from the PostgreSQL database by its ID. Use this when the user explicitly asks to forget or remove a specific memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "integer",
                        "description": "The ID of the memory to delete (from the user_memories table)",
                    },
                },
                "required": ["memory_id"],
                "additionalProperties": False,
            },
        },
    },
]

_EXECUTION_BATCH_MANAGER = ExecutionBatchManager()


# Create or reuse execution agent and dispatch instructions asynchronously
def send_message_to_agent(agent_name: str, instructions: str) -> ToolResult:
    """Send instructions to an execution agent."""
    roster = get_agent_roster()
    roster.load()
    roster.prune_duplicates()
    is_new = not roster.has_agent(agent_name)

    if is_new:
        roster.add_agent(agent_name)

    get_execution_agent_logs().record_request(agent_name, instructions)

    action = "Created" if is_new else "Reused"
    logger.info(f"{action} agent: {agent_name}")

    async def _execute_async() -> None:
        try:
            result = await _EXECUTION_BATCH_MANAGER.execute_agent(agent_name, instructions)
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
        },
    )


def remove_agent(agent_name: str, clear_logs: bool = False) -> ToolResult:
    """Remove an agent entry from the roster."""

    roster = get_agent_roster()
    roster.load()
    roster.prune_duplicates()

    removed = roster.remove_agent(agent_name)

    if removed and clear_logs:
        get_execution_agent_logs().remove_agent_logs(agent_name)

    if removed:
        logger.info("Agent removed via tool", extra={"agent_name": agent_name})
        return ToolResult(
            success=True,
            payload={
                "status": "removed",
                "agent_name": agent_name,
                "logs_cleared": bool(clear_logs),
            },
        )

    logger.info("Agent removal requested but no matching entry found", extra={"agent_name": agent_name})
    return ToolResult(
        success=False,
        payload={
            "status": "not_found",
            "agent_name": agent_name,
            "logs_cleared": False,
        },
    )


# Cache to prevent duplicate messages in quick succession
_last_telegram_messages: Dict[str, str] = {}


# Send immediate message to user and record in conversation history
async def send_message_to_user(message: str) -> ToolResult:
    """Record a user-visible reply in the conversation log and send to Telegram if available."""
    from .context import get_telegram_chat_id
    from ...services.telegram_service import get_telegram_service

    # NO TRUNCATION - let telegram_service handle splitting into multiple short messages
    # This allows Seline to send 2-3 short messages instead of one truncated message

    log = get_conversation_log()
    await log.record_reply(message)

    # If we have a Telegram chat ID, send the message immediately
    chat_id = get_telegram_chat_id()
    if chat_id:
        # Check if this is a duplicate message (prevent spam)
        last_msg = _last_telegram_messages.get(chat_id)
        if last_msg == message:
            logger.info(
                "Duplicate message detected - skipping Telegram send",
                extra={"chat_id": chat_id, "message_preview": message[:100]}
            )
            return ToolResult(
                success=True,
                payload={"status": "duplicate_skipped"},
                user_message=message,
                recorded_reply=True,
            )

        telegram_service = get_telegram_service()
        sent = await telegram_service.send_message(chat_id, message)
        if sent:
            # Cache this message to prevent duplicates
            _last_telegram_messages[chat_id] = message
            logger.info(
                f"✅ Telegram message sent to {chat_id}",
                extra={"message_length": len(message)}
            )
        else:
            logger.error(
                f"❌ Failed to send Telegram message to {chat_id}",
                extra={"chat_id": chat_id, "message_preview": message[:100]}
            )
    else:
        logger.warning(
            "⚠️ No Telegram chat_id - message will NOT be sent to Telegram!",
            extra={"message_preview": message[:100]}
        )

    return ToolResult(
        success=True,
        payload={"status": "delivered"},
        user_message=message,
        recorded_reply=True,
    )


# Format and record email draft for user review
async def send_draft(
    to: str,
    subject: str,
    body: str,
) -> ToolResult:
    """Record a draft update in the conversation log for the interaction agent."""
    log = get_conversation_log()

    message = f"To: {to}\nSubject: {subject}\n\n{body}"

    await log.record_reply(message)
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
async def wait(reason: str) -> ToolResult:
    """Wait silently and add a wait log entry that is not visible to the user."""
    log = get_conversation_log()

    # Record a dedicated wait entry so the UI knows to ignore it
    await log.record_wait(reason)


    return ToolResult(
        success=True,
        payload={
            "status": "waiting",
            "reason": reason,
        },
        recorded_reply=True,
    )


# Add a new lesson learned to the PostgreSQL database
def add_lesson_tool(category: str, problem: str, solution: str, context: Optional[str] = None) -> ToolResult:
    """Add a new lesson learned to the database when user explicitly requests it."""
    from ...services.lessons_learned import get_lessons_service

    try:
        lessons_service = get_lessons_service()
        lessons_service.add_lesson(category, problem, solution, context)

        logger.info(
            "✅ Lesson added via tool",
            extra={"category": category, "problem_preview": problem[:50]}
        )

        return ToolResult(
            success=True,
            payload={
                "status": "lesson_added",
                "category": category,
                "message": f"Lesson ajoutée dans la catégorie '{category}' et sauvegardée dans PostgreSQL."
            },
        )
    except Exception as exc:
        logger.error(
            "❌ Failed to add lesson via tool",
            extra={"error": str(exc), "category": category},
            exc_info=True
        )
        return ToolResult(
            success=False,
            payload={"error": f"Failed to add lesson: {str(exc)}"}
        )


# Retrieve lessons learned from PostgreSQL database
def get_lessons_tool(category: Optional[str] = None, min_occurrences: int = 1) -> ToolResult:
    """Retrieve lessons from the database, optionally filtered by category."""
    from ...services.lessons_learned import get_lessons_service

    try:
        lessons_service = get_lessons_service()
        lessons = lessons_service.get_lessons(category=category, min_occurrences=min_occurrences)

        if not lessons:
            message = "Aucune lesson trouvée."
            if category:
                message = f"Aucune lesson trouvée dans la catégorie '{category}'."

            return ToolResult(
                success=True,
                payload={
                    "status": "no_lessons",
                    "lessons": [],
                    "total": 0,
                    "message": message
                },
            )

        logger.info(
            "✅ Lessons retrieved via tool",
            extra={"total": len(lessons), "category": category}
        )

        return ToolResult(
            success=True,
            payload={
                "status": "lessons_found",
                "lessons": lessons,
                "total": len(lessons),
                "message": f"Trouvé {len(lessons)} lesson(s)" + (f" dans la catégorie '{category}'" if category else "")
            },
        )
    except Exception as exc:
        logger.error(
            "❌ Failed to retrieve lessons via tool",
            extra={"error": str(exc), "category": category},
            exc_info=True
        )
        return ToolResult(
            success=False,
            payload={"error": f"Failed to retrieve lessons: {str(exc)}"}
        )


# Delete a specific lesson from PostgreSQL database
def delete_lesson_tool(lesson_id: int) -> ToolResult:
    """Delete a specific lesson by ID from the database."""
    from ...services.lessons_learned import get_lessons_service

    try:
        lessons_service = get_lessons_service()

        # Check if lesson exists first
        lessons = lessons_service.get_lessons()
        lesson_exists = any(lesson.get("id") == lesson_id for lesson in lessons)

        if not lesson_exists:
            return ToolResult(
                success=False,
                payload={
                    "status": "not_found",
                    "message": f"Aucune lesson trouvée avec l'ID {lesson_id}"
                }
            )

        # Delete the lesson
        lessons_service.delete_lesson(lesson_id)

        logger.info(
            "✅ Lesson deleted via tool",
            extra={"lesson_id": lesson_id}
        )

        return ToolResult(
            success=True,
            payload={
                "status": "lesson_deleted",
                "lesson_id": lesson_id,
                "message": f"Lesson #{lesson_id} supprimée de PostgreSQL."
            },
        )
    except Exception as exc:
        logger.error(
            "❌ Failed to delete lesson via tool",
            extra={"error": str(exc), "lesson_id": lesson_id},
            exc_info=True
        )
        return ToolResult(
            success=False,
            payload={"error": f"Failed to delete lesson: {str(exc)}"}
        )


# Add or update a user memory in PostgreSQL database
def add_memory_tool(category: str, key: str, value: str, context: Optional[str] = None) -> ToolResult:
    """Add or update a contextual memory about the user."""
    from ...services.user_memory import get_user_memory_service

    try:
        memory_service = get_user_memory_service()
        memory_service.add_memory(category, key, value, context)

        logger.info(
            "✅ Memory added via tool",
            extra={"category": category, "key": key}
        )

        return ToolResult(
            success=True,
            payload={
                "status": "memory_added",
                "category": category,
                "key": key,
                "message": f"Mémoire ajoutée: {category}/{key}"
            },
        )
    except Exception as exc:
        logger.error(
            "❌ Failed to add memory via tool",
            extra={"error": str(exc), "category": category, "key": key},
            exc_info=True
        )
        return ToolResult(
            success=False,
            payload={"error": f"Failed to add memory: {str(exc)}"}
        )


# Retrieve user memories from PostgreSQL database
def get_memories_tool(category: Optional[str] = None) -> ToolResult:
    """Retrieve memories from the database, optionally filtered by category."""
    from ...services.user_memory import get_user_memory_service

    try:
        memory_service = get_user_memory_service()
        memories = memory_service.get_memories(category=category, limit=20)

        if not memories:
            message = "Aucune mémoire trouvée."
            if category:
                message = f"Aucune mémoire trouvée dans la catégorie '{category}'."

            return ToolResult(
                success=True,
                payload={
                    "status": "no_memories",
                    "memories": [],
                    "total": 0,
                    "message": message
                },
            )

        logger.info(
            "✅ Memories retrieved via tool",
            extra={"total": len(memories), "category": category}
        )

        return ToolResult(
            success=True,
            payload={
                "status": "memories_found",
                "memories": memories,
                "total": len(memories),
                "message": f"Trouvé {len(memories)} mémoire(s)" + (f" dans la catégorie '{category}'" if category else "")
            },
        )
    except Exception as exc:
        logger.error(
            "❌ Failed to retrieve memories via tool",
            extra={"error": str(exc), "category": category},
            exc_info=True
        )
        return ToolResult(
            success=False,
            payload={"error": f"Failed to retrieve memories: {str(exc)}"}
        )


# Delete a specific memory from PostgreSQL database
def delete_memory_tool(memory_id: int) -> ToolResult:
    """Delete a specific memory by ID from the database."""
    from ...services.user_memory import get_user_memory_service

    try:
        memory_service = get_user_memory_service()

        # Delete the memory
        deleted = memory_service.delete_memory(memory_id)

        if not deleted:
            return ToolResult(
                success=False,
                payload={
                    "status": "not_found",
                    "message": f"Aucune mémoire trouvée avec l'ID {memory_id}"
                }
            )

        logger.info(
            "✅ Memory deleted via tool",
            extra={"memory_id": memory_id}
        )

        return ToolResult(
            success=True,
            payload={
                "status": "memory_deleted",
                "memory_id": memory_id,
                "message": f"Mémoire #{memory_id} supprimée de PostgreSQL."
            },
        )
    except Exception as exc:
        logger.error(
            "❌ Failed to delete memory via tool",
            extra={"error": str(exc), "memory_id": memory_id},
            exc_info=True
        )
        return ToolResult(
            success=False,
            payload={"error": f"Failed to delete memory: {str(exc)}"}
        )


# Return predefined tool schemas for LLM function calling
def get_tool_schemas():
    """Return OpenAI-compatible tool schemas."""
    return TOOL_SCHEMAS


# Route tool calls to appropriate handlers with argument validation and error handling
async def handle_tool_call(name: str, arguments: Any) -> ToolResult:
    """Handle tool calls from interaction agent."""
    try:
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        elif isinstance(arguments, dict):
            args = arguments
        else:
            return ToolResult(success=False, payload={"error": "Invalid arguments format"})

        if name == "send_message_to_agent":
            return send_message_to_agent(**args)
        if name == "send_message_to_user":
            return await send_message_to_user(**args)
        if name == "send_draft":
            return await send_draft(**args)
        if name == "wait":
            return await wait(**args)
        if name == "remove_agent":
            return remove_agent(**args)
        if name == "add_lesson":
            return add_lesson_tool(**args)
        if name == "get_lessons":
            return get_lessons_tool(**args)
        if name == "delete_lesson":
            return delete_lesson_tool(**args)
        if name == "add_memory":
            return add_memory_tool(**args)
        if name == "get_memories":
            return get_memories_tool(**args)
        if name == "delete_memory":
            return delete_memory_tool(**args)

        # Note: Concatenated tool names are now detected earlier in runtime.py
        # This allows us to provide better error messages to the LLM
        logger.warning("unexpected tool", extra={"tool": name})
        return ToolResult(success=False, payload={"error": f"Unknown tool: {name}"})
    except json.JSONDecodeError:
        return ToolResult(success=False, payload={"error": "Invalid JSON"})
    except TypeError as exc:
        return ToolResult(success=False, payload={"error": f"Missing required arguments: {exc}"})
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("tool call failed", extra={"tool": name, "error": str(exc)})
        return ToolResult(success=False, payload={"error": "Failed to execute"})
