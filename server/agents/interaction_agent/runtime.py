"""Interaction Agent Runtime - handles LLM calls for user and agent turns."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, List, Optional, Set, Tuple

from .agent import build_system_prompt, prepare_message_with_history
from .tools import ToolResult, get_tool_schemas, handle_tool_call
from ...config import get_settings
from ...services.conversation import get_conversation_log, get_working_memory_log
from ...openrouter_client import request_chat_completion
from ...logging_config import logger


@dataclass
class InteractionResult:
    """Result from the interaction agent."""

    success: bool
    response: str
    error: Optional[str] = None
    execution_agents_used: int = 0


@dataclass
class _ToolCall:
    """Parsed tool invocation from an LLM response."""

    identifier: Optional[str]
    name: str
    arguments: Dict[str, Any]


@dataclass
class _LoopSummary:
    """Aggregate information produced by the interaction loop."""

    last_assistant_text: str = ""
    user_messages: List[str] = field(default_factory=list)
    tool_names: List[str] = field(default_factory=list)
    execution_agents: Set[str] = field(default_factory=set)


class InteractionAgentRuntime:
    """Manages the interaction agent's request processing."""

    MAX_TOOL_ITERATIONS = 8

    # Initialize interaction agent runtime with settings and service dependencies
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.openrouter_api_key
        self.model = settings.interaction_agent_model
        self.settings = settings
        self.conversation_log = get_conversation_log()
        self.working_memory_log = get_working_memory_log()
        self.tool_schemas = get_tool_schemas()

        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable."
            )

    # Main entry point for processing user messages through the LLM interaction loop
    async def execute(self, user_message: str) -> InteractionResult:
        """Handle a user-authored message."""

        # I1 (LTM design §8.9): ingress scrub first; nothing below may touch the raw string.
        observed_at = datetime.now(timezone.utc)
        text, ingress_findings = self._ingress_scrub(user_message)
        del user_message

        try:
            transcript_before = self._load_conversation_transcript()
            self.conversation_log.record_user_message(text)

            prepared = self._prepare_memory(text, "user_message", ingress_findings, observed_at)
            system_prompt = build_system_prompt()
            messages = prepare_message_with_history(
                text, transcript_before, message_type="user", **_memory_sections(prepared)
            )
            if prepared is not None:
                self._schedule_memory_ingest(prepared, _last_reply(transcript_before))

            logger.info("Processing user message through interaction agent")
            summary = await self._run_interaction_loop(system_prompt, messages)

            final_response = self._finalize_response(summary)

            if final_response and not summary.user_messages:
                self.conversation_log.record_reply(final_response)

            return InteractionResult(
                success=True,
                response=final_response,
                execution_agents_used=len(summary.execution_agents),
            )

        except Exception as exc:
            logger.error("Interaction agent failed", extra={"error": str(exc)})
            return InteractionResult(
                success=False,
                response="",
                error=str(exc),
            )

    # Handle incoming messages from execution agents and generate appropriate responses
    async def handle_agent_message(self, agent_message: str) -> InteractionResult:
        """Process a status update emitted by an execution agent."""

        # I1: same ingress boundary for execution-agent / watcher messages. Agent turns never ingest (D6).
        observed_at = datetime.now(timezone.utc)
        text, ingress_findings = self._ingress_scrub(agent_message)
        del agent_message

        try:
            transcript_before = self._load_conversation_transcript()
            self.conversation_log.record_agent_message(text)

            prepared = self._prepare_memory(text, "agent_message", ingress_findings, observed_at)
            system_prompt = build_system_prompt()
            messages = prepare_message_with_history(
                text, transcript_before, message_type="agent", **_memory_sections(prepared)
            )

            logger.info("Processing execution agent results")
            summary = await self._run_interaction_loop(system_prompt, messages)

            final_response = self._finalize_response(summary)

            if final_response and not summary.user_messages:
                self.conversation_log.record_reply(final_response)

            return InteractionResult(
                success=True,
                response=final_response,
                execution_agents_used=len(summary.execution_agents),
            )

        except Exception as exc:
            logger.error("Interaction agent (agent message) failed", extra={"error": str(exc)})
            return InteractionResult(
                success=False,
                response="",
                error=str(exc),
            )

    # Core interaction loop that handles LLM calls and tool executions until completion
    async def _run_interaction_loop(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
    ) -> _LoopSummary:
        """Iteratively query the LLM until it issues a final response."""

        summary = _LoopSummary()

        for iteration in range(self.MAX_TOOL_ITERATIONS):
            response = await self._make_llm_call(system_prompt, messages)
            assistant_message = self._extract_assistant_message(response)

            assistant_content = (assistant_message.get("content") or "").strip()
            if assistant_content:
                summary.last_assistant_text = assistant_content

            raw_tool_calls = assistant_message.get("tool_calls") or []
            parsed_tool_calls = self._parse_tool_calls(raw_tool_calls)

            assistant_entry: Dict[str, Any] = {
                "role": "assistant",
                "content": assistant_message.get("content", "") or "",
            }
            if raw_tool_calls:
                assistant_entry["tool_calls"] = raw_tool_calls
            messages.append(assistant_entry)

            if not parsed_tool_calls:
                break

            for tool_call in parsed_tool_calls:
                summary.tool_names.append(tool_call.name)

                if tool_call.name == "send_message_to_agent":
                    agent_name = tool_call.arguments.get("agent_name")
                    if isinstance(agent_name, str) and agent_name:
                        summary.execution_agents.add(agent_name)

                result = self._execute_tool(tool_call)

                if result.user_message:
                    summary.user_messages.append(result.user_message)

                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call.identifier or tool_call.name,
                    "content": self._format_tool_result(tool_call, result),
                }
                messages.append(tool_message)
        else:
            raise RuntimeError("Reached tool iteration limit without final response")

        if not summary.user_messages and not summary.last_assistant_text:
            logger.warning("Interaction loop exited without assistant content")

        return summary

    # Load conversation history, preferring summarized version if available
    def _ingress_scrub(self, text: str) -> Tuple[str, List[Any]]:
        if not self.settings.ingress_scrub_enabled:
            return text, []
        from ...services.memory.privacy import ingress_scrub

        return ingress_scrub(text)

    def _prepare_memory(self, text: str, source_kind: str, ingress_findings: List[Any], observed_at: datetime) -> Any:
        """LTM prepare_turn (sync: P0, forget, retrieval). Fails open for chat: any error means no memory block."""
        if not self.settings.ltm_enabled:
            return None
        try:
            from ...services.memory import get_memory_service

            return get_memory_service().prepare_turn(text, source_kind, ingress_findings, observed_at)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("ltm prepare_turn failed", extra={"error": type(exc).__name__})
            return None

    def _schedule_memory_ingest(self, prepared: Any, prev_reply: Optional[str]) -> None:
        try:
            from ...services.memory import get_memory_service

            get_memory_service().schedule_ingest(prepared, prev_reply=prev_reply)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("ltm schedule_ingest failed", extra={"error": type(exc).__name__})

    def _load_conversation_transcript(self) -> str:
        if self.settings.summarization_enabled:
            rendered = self.working_memory_log.render_transcript()
            if rendered.strip():
                return rendered
        return self.conversation_log.load_transcript()

    # Execute API call to OpenRouter with system prompt, messages, and tool schemas
    async def _make_llm_call(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Make an LLM call via OpenRouter."""

        logger.debug(
            "Interaction agent calling LLM",
            extra={"model": self.model, "tools": len(self.tool_schemas)},
        )
        return await request_chat_completion(
            model=self.model,
            messages=messages,
            system=system_prompt,
            api_key=self.api_key,
            tools=self.tool_schemas,
        )

    # Extract the assistant's message from the OpenRouter API response structure
    def _extract_assistant_message(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Return the assistant message from the raw response payload."""

        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("LLM response did not include an assistant message")
        return message

    # Convert raw LLM tool calls into structured _ToolCall objects with validation
    def _parse_tool_calls(self, raw_tool_calls: List[Dict[str, Any]]) -> List[_ToolCall]:
        """Normalize tool call payloads from the LLM."""

        parsed: List[_ToolCall] = []
        for raw in raw_tool_calls:
            function_block = raw.get("function") or {}
            name = function_block.get("name")
            if not isinstance(name, str) or not name:
                logger.warning("Skipping tool call without name", extra={"tool": raw})
                continue

            arguments, error = self._parse_tool_arguments(function_block.get("arguments"))
            if error:
                logger.warning("Tool call arguments invalid", extra={"tool": name, "error": error})
                parsed.append(
                    _ToolCall(
                        identifier=raw.get("id"),
                        name=name,
                        arguments={"__invalid_arguments__": error},
                    )
                )
                continue

            parsed.append(
                _ToolCall(identifier=raw.get("id"), name=name, arguments=arguments)
            )

        return parsed

    # Parse and validate tool arguments from various formats (dict, JSON string, etc.)
    def _parse_tool_arguments(
        self, raw_arguments: Any
    ) -> tuple[Dict[str, Any], Optional[str]]:
        """Convert tool arguments into a dictionary, reporting errors."""

        if raw_arguments is None:
            return {}, None

        if isinstance(raw_arguments, dict):
            return raw_arguments, None

        if isinstance(raw_arguments, str):
            if not raw_arguments.strip():
                return {}, None
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                return {}, f"invalid json: {exc}"
            if isinstance(parsed, dict):
                return parsed, None
            return {}, "decoded arguments were not an object"

        return {}, f"unsupported argument type: {type(raw_arguments).__name__}"

    # Execute tool calls with error handling and logging, returning standardized results
    def _execute_tool(self, tool_call: _ToolCall) -> ToolResult:
        """Execute a tool call and convert low-level errors into structured results."""

        if "__invalid_arguments__" in tool_call.arguments:
            error = tool_call.arguments["__invalid_arguments__"]
            self._log_tool_invocation(tool_call, stage="rejected", detail={"error": error})
            return ToolResult(success=False, payload={"error": error})

        try:
            self._log_tool_invocation(tool_call, stage="start")
            result = handle_tool_call(tool_call.name, tool_call.arguments)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Tool execution crashed",
                extra={"tool": tool_call.name, "error": str(exc)},
            )
            self._log_tool_invocation(
                tool_call,
                stage="error",
                detail={"error": str(exc)},
            )
            return ToolResult(success=False, payload={"error": str(exc)})

        if not isinstance(result, ToolResult):
            logger.warning(
                "Tool did not return ToolResult; coercing",
                extra={"tool": tool_call.name},
            )
            wrapped = ToolResult(success=True, payload=result)
            self._log_tool_invocation(tool_call, stage="done", result=wrapped)
            return wrapped

        status = "success" if result.success else "error"
        logger.debug(
            "Tool executed",
            extra={
                "tool": tool_call.name,
                "status": status,
            },
        )
        self._log_tool_invocation(tool_call, stage="done", result=result)
        return result

    # Format tool execution results into JSON for LLM consumption
    def _format_tool_result(self, tool_call: _ToolCall, result: ToolResult) -> str:
        """Render a tool execution result back to the LLM."""

        payload: Dict[str, Any] = {
            "tool": tool_call.name,
            "status": "success" if result.success else "error",
            "arguments": {
                key: value
                for key, value in tool_call.arguments.items()
                if key != "__invalid_arguments__"
            },
        }

        if result.payload is not None:
            key = "result" if result.success else "error"
            payload[key] = result.payload

        return self._safe_json_dump(payload)

    # Safely serialize objects to JSON with fallback to string representation
    def _safe_json_dump(self, payload: Any) -> str:
        """Serialize payload to JSON, falling back to repr on failure."""

        try:
            return json.dumps(payload, default=str)
        except TypeError:
            return repr(payload)

    # Log tool execution stages (start, done, error) with structured metadata
    def _log_tool_invocation(
        self,
        tool_call: _ToolCall,
        *,
        stage: str,
        result: Optional[ToolResult] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit structured logs for tool lifecycle events."""

        cleaned_args = {
            key: value
            for key, value in tool_call.arguments.items()
            if key != "__invalid_arguments__"
        }

        log_payload: Dict[str, Any] = {
            "tool": tool_call.name,
            "stage": stage,
            "arguments": cleaned_args,
        }

        if result is not None:
            log_payload["success"] = result.success
            if result.payload is not None:
                log_payload["payload"] = result.payload

        if detail:
            log_payload.update(detail)

        if stage == "done":
            logger.info(f"Tool '{tool_call.name}' completed")
        elif stage in {"error", "rejected"}:
            logger.warning(f"Tool '{tool_call.name}' {stage}")
        else:
            logger.debug(f"Tool '{tool_call.name}' {stage}")

    # Determine final user-facing response from interaction loop summary
    def _finalize_response(self, summary: _LoopSummary) -> str:
        """Decide what text should be exposed to the user as the final reply."""

        if summary.user_messages:
            return summary.user_messages[-1]

        return summary.last_assistant_text


def _memory_sections(prepared: Any) -> Dict[str, Any]:
    """Extra prepare_message_with_history kwargs; empty when LTM is off, so the call is unchanged."""
    if prepared is None:
        return {}
    return {"long_term_memory": prepared.ltm_block or None, "memory_notices": list(prepared.notices) or None}


_REPLY_RX = re.compile(r"<poke_reply(?: [^>]*)?>(.*?)</poke_reply>", re.S)


def _last_reply(transcript: str) -> Optional[str]:
    """Previous assistant reply (context for the extractor, never a source)."""
    replies = _REPLY_RX.findall(transcript or "")
    return unescape(replies[-1]) if replies else None
