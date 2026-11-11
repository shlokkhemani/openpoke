"""Tool definitions for interaction agent."""

import asyncio
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Literal, Optional

from ...config import get_settings
from ...logging_config import logger
from ...services.agents import indexer
from ...services.agents.retrieval import RetrievalConfig
from ...services.agents.store import get_agent_store
from ...services.conversation import get_conversation_log
from ...services.execution import get_execution_agent_logs
from ...services.triggers import get_trigger_service
from ..execution_agent.batch_manager import ExecutionBatchManager
from .roster_view import legacy_tool_schemas, retrieve_cards


@dataclass
class ToolResult:
    """Standardized payload returned by interaction-agent tools."""

    success: bool
    payload: Any = None
    user_message: Optional[str] = None
    recorded_reply: bool = False

# Tool schemas for OpenRouter (production: dispatch by ``agent_id`` or create by ``name``).
# The pre-id ``agent_name`` schemas live in ``roster_view.legacy_tool_schemas()``.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "send_message_to_agent",
            "description": "Deliver instructions to an execution agent. Pass `agent_id` to reuse an existing agent, or `name` to create a new one; never both. Creating returns the new agent's id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Id of an existing agent to reuse (e.g. 'ag_k3m9x2pq'), exactly as shown in the active agents.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Name for a new agent that says who and what (e.g. 'Email Alice Chen re offsite'). Only when creating.",
                    },
                    "instructions": {"type": "string", "description": "Instructions for the agent to execute."},
                },
                "required": ["instructions"],
                "additionalProperties": False,
            },
        },
    },
    *legacy_tool_schemas()[1:],
]

# The hybrid-mode search tool: the model's query only; always the closest K agents (K from settings).
SEARCH_AGENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_agents",
        "description": "Search all agents by who and what. Use when none of the active agents shown fits the request, before creating a new agent. Works once per message.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Who and what the task is about (e.g. 'Alice Chen offsite email').",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}
HYBRID_TOOL_SCHEMAS = [*TOOL_SCHEMAS, SEARCH_AGENTS_SCHEMA]

_EXECUTION_BATCH_MANAGER = ExecutionBatchManager()

TurnType = Literal["user", "agent"]

# Which kind of IA turn is running, set by the runtime for the duration of one turn. A ContextVar
# keeps concurrent turns (each in its own asyncio task) from seeing each other's value.
_TURN_TYPE: ContextVar[TurnType] = ContextVar("ia_turn_type", default="user")


def current_turn_type() -> TurnType:
    """The type of the IA turn in progress ("user" when none is set)."""
    return _TURN_TYPE.get()


@contextmanager
def turn_type(value: TurnType) -> Iterator[None]:
    """Mark the code inside as running for a ``value`` turn; restores the previous value after."""
    if value not in ("user", "agent"):
        raise ValueError(f"unknown turn type {value!r}")
    token = _TURN_TYPE.set(value)
    try:
        yield
    finally:
        _TURN_TYPE.reset(token)


# Whether this turn may call ``search_agents`` and whether it already did: None = not a hybrid turn,
# False = may search, True = searched. A ContextVar keeps concurrent turns apart, like the turn type.
_SEARCHED: ContextVar[Optional[bool]] = ContextVar("ia_searched", default=None)


@contextmanager
def search_turn(enabled: bool) -> Iterator[None]:
    """Run the code inside as one turn with (``enabled``) a fresh one-search budget; restores after."""
    token = _SEARCHED.set(False if enabled else None)
    try:
        yield
    finally:
        _SEARCHED.reset(token)


ERR_ALREADY_SEARCHED = "Already searched this turn. If no agent fits, create one with `name`."
ERR_BLANK_QUERY = "Pass a non-empty query describing the task or person."


# ``send_message_to_agent`` error texts; the eval harness's id tool stub returns the same ones.
ERR_BOTH_ID_AND_NAME = "Pass either agent_id (to reuse an agent) or name (to create one), not both."
ERR_NEITHER_ID_NOR_NAME = "Pass agent_id to reuse an existing agent, or name to create a new one."
# ``.format(agent_id=...)``
ERR_UNKNOWN_AGENT_ID = (
    "unknown agent_id {agent_id!r}: use an id from the active agents, or pass name to create a new agent."
)


def _error(message: str) -> ToolResult:
    return ToolResult(success=False, payload={"error": message})


def _given(value: Any) -> Optional[str]:
    """A non-empty string argument, stripped; None when absent or blank (same rule as grading)."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


# Reuse an agent by id or create one by name, then dispatch instructions asynchronously
def send_message_to_agent(
    instructions: str, agent_id: Optional[str] = None, name: Optional[str] = None
) -> ToolResult:
    """Send instructions to an execution agent: ``agent_id`` reuses it, ``name`` creates one."""
    agent_id, name = _given(agent_id), _given(name)
    if agent_id and name:
        return _error(ERR_BOTH_ID_AND_NAME)
    if not agent_id and not name:
        return _error(ERR_NEITHER_ID_NOR_NAME)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("No running event loop available for async execution")
        return _error("No event loop available")

    store = get_agent_store()
    if agent_id:
        agent = store.get(agent_id)
        if agent is None:
            return _error(ERR_UNKNOWN_AGENT_ID.format(agent_id=agent_id))
        is_new = False
    else:
        agent = store.create_agent(name)
        is_new = True
        try:
            indexer.index_agent(agent.id, [])  # a new agent has no triggers yet
        except Exception as exc:
            logger.warning(f"[{agent.id}] search index refresh failed: {exc}")

    use = "agent" if current_turn_type() == "agent" else "user"
    store.record_use(agent.id, use, datetime.now(timezone.utc))
    get_execution_agent_logs().record_request(agent.id, instructions)

    action = "Created" if is_new else "Reused"
    logger.info(f"{action} agent: {agent.name} ({agent.id})")
    target_id, label = agent.id, agent.name

    async def _execute_async() -> None:
        try:
            result = await _EXECUTION_BATCH_MANAGER.execute_agent(target_id, instructions)
            status = "SUCCESS" if result.success else "FAILED"
            logger.info(f"Agent '{label}' ({target_id}) completed: {status}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Agent '{label}' ({target_id}) failed: {str(exc)}")

    loop.create_task(_execute_async())

    return ToolResult(
        success=True,
        payload={"status": "submitted", "agent_id": agent.id, "new_agent_created": is_new},
    )


# Find the closest agents to a query: the pure core, shared with the eval harness
def search_agents_result(query: Any, store, embedder, cfg: RetrievalConfig, triggers_for) -> ToolResult:
    """Cards of the agents closest to ``query`` with a note; a blank query is an error. No budget here."""
    text = _given(query)
    if text is None:
        return _error(ERR_BLANK_QUERY)
    n_total, ids, cards = retrieve_cards(store, embedder, text, cfg, triggers_for)
    note = f"Closest {len(ids)} of {n_total} agents; if none handles this task, create a new agent with `name`."
    return ToolResult(success=True, payload={"note": note, "agents": cards})


# Find the closest agents to a query, once per hybrid turn
def search_agents_tool(query: Any = None) -> ToolResult:
    """Return the closest agents to ``query`` as cards; the budget is spent only by a real search."""
    if _given(query) is None:
        return _error(ERR_BLANK_QUERY)
    if _SEARCHED.get():
        return _error(ERR_ALREADY_SEARCHED)
    result = search_agents_result(
        query, get_agent_store(), indexer.ready_embedder(),
        RetrievalConfig.from_settings(get_settings()), get_trigger_service().list_for_agent,
    )
    _SEARCHED.set(True)
    return result


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

        if name == "send_message_to_agent":
            if "agent_name" in args:
                return _error(
                    "agent_name is not a parameter: pass agent_id to reuse an existing agent, "
                    "or name to create a new one."
                )
            return send_message_to_agent(**args)
        if name == "search_agents" and _SEARCHED.get() is not None:
            return search_agents_tool(**args)
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
