"""Interaction Agent Runtime - handles LLM calls for user and agent turns."""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

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

        try:
            transcript_before = self._load_conversation_transcript()
            self.conversation_log.record_user_message(user_message)

            self._turn_type = "user"
            turn_text = user_message
            if self.settings.budgeted_context:
                turn_text = self._bound_turn_text(user_message)

            system_prompt = build_system_prompt()
            messages = prepare_message_with_history(
                turn_text, transcript_before, message_type="user"
            )

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

        try:
            transcript_before = self._load_conversation_transcript()
            self.conversation_log.record_agent_message(agent_message)

            self._turn_type = "agent"
            turn_text = agent_message
            if self.settings.budgeted_context:
                turn_text = self._bound_turn_text(agent_message)

            system_prompt = build_system_prompt()
            messages = prepare_message_with_history(
                turn_text, transcript_before, message_type="agent"
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

    # Budgeted: the current-turn slot (a user paste or a merged worker batch) is the one prompt part the
    # history budget does not govern. Bound it; the full text was just written to the log and is recallable.
    def _bound_turn_text(self, text: str) -> str:
        from .context.history import _preview
        from ...utils.tokens import chars_for_tokens

        cap = chars_for_tokens(self.settings.context_turn_max_tokens)
        if len(text) <= cap:
            return text
        entry_id = sum(1 for _ in self.conversation_log.iter_entries()) - 1
        logger.info("Budgeted turn text bounded", extra={"chars": len(text), "entry_id": entry_id})
        return (f"[This message is {len(text):,} characters; shown as a head/tail preview. It is entry id={entry_id} "
                f"in the conversation log: call recall_history with that id to read parts of it in full.]\n"
                + _preview(text, cap))

    def _worker_reported_draft(self) -> bool:
        """True if any worker callback in the log mentions a draft (so showing/re-showing one is legitimate)."""
        for tag, _, payload in self.conversation_log.iter_entries():
            if tag == "agent_message" and "draft" in payload.lower():
                return True
        return False

    # Core interaction loop that handles LLM calls and tool executions until completion
    async def _run_interaction_loop(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
    ) -> _LoopSummary:
        """Iteratively query the LLM until it issues a final response."""

        summary = _LoopSummary()
        budgeted = self.settings.budgeted_context
        dispatched_this_turn: set = set()
        recalls_this_turn = 0
        result_tokens_this_turn = 0

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

            round_names = [tc.name for tc in parsed_tool_calls]
            for tool_call in parsed_tool_calls:
                summary.tool_names.append(tool_call.name)

                if tool_call.name == "send_message_to_agent":
                    agent_name = tool_call.arguments.get("agent_name")
                    if isinstance(agent_name, str) and agent_name:
                        summary.execution_agents.add(agent_name)
                        if budgeted and agent_name in dispatched_this_turn:
                            # Already running from this same turn: re-dispatching would start a second, competing
                            # run and a second draft. Tell the model to let the callback arrive instead.
                            result = ToolResult(success=False, payload={
                                "error": f"'{agent_name}' was already dispatched in this turn and is still running; "
                                         f"its result will arrive as a separate agent message. Do not dispatch it again now."})
                            messages.append({"role": "tool", "tool_call_id": tool_call.identifier or tool_call.name,
                                             "content": self._format_tool_result(tool_call, result)})
                            continue
                        dispatched_this_turn.add(agent_name)

                if budgeted and tool_call.name == "recall_history" and recalls_this_turn >= self.settings.recall_calls_per_turn:
                    result = ToolResult(success=False, payload={
                        "error": (f"recall_history limit for this turn ({self.settings.recall_calls_per_turn}) reached. Paging cannot "
                                  f"read a large entry within one context. For synthesis call digest_entry with the entry ids; for "
                                  f"verbatim use, pass the entry id to a worker instead of reading it.")})
                elif budgeted and tool_call.name == "digest_entry":
                    from .tools import digest_entry

                    self._log_tool_invocation(tool_call, stage="start")
                    args = tool_call.arguments if isinstance(tool_call.arguments, dict) else {}
                    result = await digest_entry(args.get("entry_ids"), args.get("question", ""), entry_id=args.get("entry_id"))
                elif budgeted and tool_call.name == "send_draft" and getattr(self, "_turn_type", "user") == "user" \
                        and not self._worker_reported_draft():
                    # send_draft only displays; the draft itself must come from a worker. Composing one here would show
                    # the user an email that does not exist in Gmail.
                    result = ToolResult(success=False, payload={
                        "error": "No worker has created a draft yet, so there is nothing to show. send_draft only displays a "
                                 "draft a worker already created. Dispatch a worker with send_message_to_agent to create the "
                                 "draft; it will report back with the draft id and text, and you show it then."})
                else:
                    result = self._execute_tool(tool_call)

                if result.user_message:
                    summary.user_messages.append(result.user_message)

                if budgeted and tool_call.name == "recall_history" and result.success:
                    recalls_this_turn += 1
                content = self._format_tool_result(tool_call, result)
                if budgeted:
                    from ...utils.tokens import estimate_tokens

                    cost = estimate_tokens(content)
                    if result_tokens_this_turn + cost > self.settings.turn_tool_result_budget_tokens:
                        # Backstop only: with digest and by-reference passing this should not trigger in normal use.
                        content = self._format_tool_result(tool_call, ToolResult(success=False, payload={
                            "error": "turn tool-result budget exhausted; answer with what you have, or digest instead of reading"}))
                        cost = estimate_tokens(content)
                    result_tokens_this_turn += cost
                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call.identifier or tool_call.name,
                    "content": content,
                }
                messages.append(tool_message)

            if budgeted:
                # `wait` means "stay silent": the turn is over, there is nothing to re-plan after it.
                if round_names and all(n == "wait" for n in round_names):
                    break
                # A dispatch has been handed off and the user has been told; the only thing another round
                # could add is a redundant status line. Stop here (legacy spends one more call to say "submitted").
                if "send_message_to_agent" in round_names and (
                    summary.user_messages or assistant_content
                    or any(n in ("send_message_to_user", "send_draft") for n in round_names)
                ):
                    break
        else:
            raise RuntimeError("Reached tool iteration limit without final response")

        if not summary.user_messages and not summary.last_assistant_text:
            logger.warning("Interaction loop exited without assistant content")

        return summary

    # Load conversation history, preferring summarized version if available
    def _load_conversation_transcript(self) -> str:
        if self.settings.budgeted_context:
            from .context.history import build_history

            built = build_history()
            logger.info(
                "Budgeted context assembled",
                extra={
                    "inline": built.inline_entries,
                    "truncated": built.truncated_entries,
                    "indexed": built.indexed_entries,
                    "tokens": built.estimated_tokens,
                },
            )
            return built.transcript
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
