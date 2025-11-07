"""Simplified Execution Agent Runtime."""

import inspect
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from server.agents.execution_agent.agent import ExecutionAgent
from server.agents.execution_agent.tools import get_tool_schemas, get_tool_registry
from server.agents.tool_parsing import extract_tool_calls
from server.agents.tool_formatting import format_tool_result
from server.config import get_settings
from server.openrouter_client import request_chat_completion
from server.logging_config import logger
from server.utils.json_utils import safe_json_dump, safe_json_load
from server.utils.exceptions import AgentExecutionError, OpenPokeError, ToolExecutionError
from server.utils.tool_validation import get_execution_tool_names, split_known_tools


@dataclass
class ExecutionResult:
    """Result from an execution agent."""
    agent_name: str
    success: bool
    response: str
    error: Optional[str] = None
    tools_executed: List[str] = field(default_factory=list)


class ExecutionAgentRuntime:
    """Manages the execution of a single agent request."""

    MAX_TOOL_ITERATIONS = 5
    _REPEATED_PLAN_THRESHOLD = 2

    # Initialize execution agent runtime with settings, tools, and agent instance
    def __init__(self, agent_name: str):
        settings = get_settings()
        self.agent = ExecutionAgent(agent_name)
        self.api_key = settings.openrouter_api_key
        self.model = settings.execution_agent_model
        self.tool_registry = get_tool_registry(agent_name=agent_name)
        self.tool_schemas = get_tool_schemas()

        if not self.api_key:
            raise ValueError("OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable.")

    # Main execution loop for running agent with LLM calls and tool execution
    async def execute(self, instructions: str) -> ExecutionResult:
        """Execute the agent with given instructions."""
        try:
            # Build system prompt with history
            system_prompt = self.agent.build_system_prompt_with_history()

            # Start conversation with the instruction
            messages = [{"role": "user", "content": instructions}]
            tools_executed: List[str] = []
            final_response: Optional[str] = None
            plan_signatures: Dict[Tuple[str, Tuple[Tuple[str, Any], ...]], int] = {}
            executed_tool_signatures: set[Tuple[str, Any]] = set()
            stop_requested = False

            for iteration in range(self.MAX_TOOL_ITERATIONS):
                logger.debug(
                    f"[{self.agent.name}] Requesting plan (iteration {iteration + 1})",
                    extra={"agent": self.agent.name, "iteration": iteration + 1}
                )
                response = await self._make_llm_call(system_prompt, messages, with_tools=True)
                assistant_message = response.get("choices", [{}])[0].get("message", {})

                if not assistant_message:
                    raise RuntimeError("LLM response did not include an assistant message")

                raw_tool_calls = assistant_message.get("tool_calls", []) or []
                parsed_tool_calls = self._extract_tool_calls(raw_tool_calls)

                # Limit to single tool call to prevent combination issues
                if len(parsed_tool_calls) > 1:
                    logger.warning("Multiple tool calls detected, using only the first one: %s", [tc.get("name") for tc in parsed_tool_calls])
                    parsed_tool_calls = parsed_tool_calls[:1]
                    # Also limit raw_tool_calls to match parsed_tool_calls
                    raw_tool_calls = raw_tool_calls[:1]

                assistant_entry: Dict[str, Any] = {
                    "role": "assistant",
                    "content": assistant_message.get("content", "") or "",
                }
                if raw_tool_calls:
                    assistant_entry["tool_calls"] = raw_tool_calls
                messages.append(assistant_entry)

                plan_signature = self._build_plan_signature(
                    assistant_entry["content"], parsed_tool_calls
                )

                if plan_signature:
                    plan_signatures[plan_signature] = plan_signatures.get(plan_signature, 0) + 1
                    if plan_signatures[plan_signature] >= self._REPEATED_PLAN_THRESHOLD:
                        logger.info(
                            f"[{self.agent.name}] Repeated plan detected; terminating early after {iteration + 1} iterations"
                        )
                        final_response = assistant_entry["content"] or "Plan repeated; no further action taken."
                        stop_requested = True

                if not parsed_tool_calls:
                    final_response = assistant_entry["content"] or "No action required."
                    stop_requested = True

                if stop_requested:
                    break

                for tool_call in parsed_tool_calls:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("arguments", {})
                    call_id = tool_call.get("id")

                    if not tool_name:
                        logger.warning("Tool call missing name: %s", tool_call)
                        failure = {"error": "Tool call missing name; unable to execute."}
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": call_id or "unknown_tool",
                            "content": self._format_tool_result(
                                tool_name or "<unknown>", False, failure, tool_args
                            ),
                        }
                        messages.append(tool_message)
                        continue

                    # Check for invalid arguments marker from validation
                    if "__invalid_arguments__" in tool_args:
                        error_message = tool_args["__invalid_arguments__"]
                        logger.warning(f"[{self.agent.name}] Invalid tool call detected: {error_message}")
                        failure = {"error": error_message}
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": call_id or tool_name,
                            "content": self._format_tool_result(
                                tool_name, False, failure, {}
                            ),
                        }
                        messages.append(tool_message)
                        continue

                    tool_signature = self._build_tool_signature(tool_name, tool_args)

                    if tool_signature in executed_tool_signatures:
                        logger.info(
                            f"[{self.agent.name}] Identical tool invocation detected; ending execution early"
                        )
                        final_response = assistant_entry["content"] or "Repeated tool invocation; stopping."
                        stop_requested = True
                        break

                    executed_tool_signatures.add(tool_signature)
                    tools_executed.append(tool_name)
                    self._log_tool_invocation(tool_name, stage="start", arguments=tool_args)

                    try:
                        success, result = await self._execute_tool(tool_name, tool_args)
                    except ToolExecutionError as exc:
                        success = False
                        result = {"error": str(exc)}
                    except (OpenPokeError, asyncio.CancelledError):
                        raise
                    except Exception as exc:
                        logger.exception(
                            f"[{self.agent.name}] Tool {tool_name} raised an unexpected error",
                            extra={
                                "agent": self.agent.name,
                                "tool": tool_name,
                                "error": str(exc),
                                "error_type": type(exc).__name__,
                            },
                        )
                        raise AgentExecutionError(
                            f"Tool '{tool_name}' crashed unexpectedly",
                            agent_name=self.agent.name,
                            details={
                                "tool": tool_name,
                                "arguments": tool_args,
                                "error": str(exc),
                                "error_type": type(exc).__name__,
                            },
                        ) from exc

                    if success:
                        self._log_tool_invocation(tool_name, stage="done", arguments=tool_args, result=result)
                        record_payload = safe_json_dump(result)
                    else:
                        error_detail = result.get("error") if isinstance(result, dict) else str(result)
                        self._log_tool_invocation(tool_name, stage="error", arguments=tool_args, detail={"error": error_detail})
                        record_payload = error_detail

                    self.agent.record_tool_execution(
                        tool_name,
                        safe_json_dump(tool_args),
                        record_payload or ""
                    )

                    tool_message = {
                        "role": "tool",
                        "tool_call_id": call_id or tool_name,
                        "content": self._format_tool_result(tool_name, success, result, tool_args),
                    }
                    messages.append(tool_message)

                if stop_requested:
                    break

            else:
                raise RuntimeError("Reached tool iteration limit without final response")

            if final_response is None:
                raise RuntimeError("LLM did not return a final response")

            self.agent.record_response(final_response)

            return ExecutionResult(
                agent_name=self.agent.name,
                success=True,
                response=final_response,
                tools_executed=tools_executed
            )

        except (ValueError, KeyError, TypeError) as e:
            # Handle expected data validation errors
            logger.warning(
                f"[{self.agent.name}] Data validation error",
                extra={"error": str(e), "error_type": type(e).__name__}
            )
            error_msg = f"Invalid data: {str(e)}"
            self.agent.record_response(f"Error: {error_msg}")
            return ExecutionResult(
                agent_name=self.agent.name,
                success=False,
                response=f"Failed to complete task: {error_msg}",
                error=error_msg
            )
        except RuntimeError as e:
            # Handle iteration limits and LLM response errors
            logger.warning(
                f"[{self.agent.name}] Runtime error",
                extra={"error": str(e)}
            )
            error_msg = str(e)
            self.agent.record_response(f"Error: {error_msg}")
            return ExecutionResult(
                agent_name=self.agent.name,
                success=False,
                response=f"Failed to complete task: {error_msg}",
                error=error_msg
            )
        except AgentExecutionError as e:
            # Handle agent-specific errors
            logger.error(
                f"[{self.agent.name}] Agent execution error",
                extra={"error": str(e), "agent": e.agent_name, "details": e.details},
                exc_info=True
            )
            error_msg = str(e)
            self.agent.record_response(f"Error: {error_msg}")
            return ExecutionResult(
                agent_name=self.agent.name,
                success=False,
                response=f"Failed to complete task: {error_msg}",
                error=error_msg
            )

    # Execute OpenRouter API call with system prompt, messages, and optional tool schemas
    async def _make_llm_call(self, system_prompt: str, messages: List[Dict], with_tools: bool) -> Dict:
        """Make an LLM call."""
        tools_to_send = self.tool_schemas if with_tools else None
        logger.debug(
            f"[{self.agent.name}] Calling LLM",
            extra={"agent": self.agent.name, "model": self.model, "tools_count": len(tools_to_send) if tools_to_send else 0}
        )
        return await request_chat_completion(
            model=self.model,
            messages=messages,
            system=system_prompt,
            api_key=self.api_key,
            tools=tools_to_send
        )

    # Parse and validate tool calls from LLM response into structured format
    def _extract_tool_calls(self, raw_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract tool calls from an assistant message."""
        known_tools = get_execution_tool_names()
        return extract_tool_calls(raw_tools, known_tools)

    @staticmethod
    def _freeze_for_signature(value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(
                sorted(
                    (key, ExecutionAgentRuntime._freeze_for_signature(val))
                    for key, val in value.items()
                )
            )
        if isinstance(value, (list, tuple)):
            return tuple(ExecutionAgentRuntime._freeze_for_signature(item) for item in value)
        if isinstance(value, set):
            return tuple(
                sorted(ExecutionAgentRuntime._freeze_for_signature(item) for item in value)
            )
        return value

    def _build_plan_signature(
        self,
        content: str,
        tool_calls: List[Dict[str, Any]],
    ) -> Tuple[str, Tuple[Tuple[str, Any], ...]]:
        normalized_content = (content or "").strip()
        frozen_tools = tuple(
            (
                call.get("name", ""),
                self._freeze_for_signature(call.get("arguments")),
            )
            for call in tool_calls
        )
        return normalized_content, frozen_tools

    def _build_tool_signature(self, name: str, arguments: Dict[str, Any]) -> Tuple[str, Any]:
        return name, self._freeze_for_signature(arguments or {})

    # Format tool execution results into JSON structure for LLM consumption
    def _format_tool_result(
        self,
        tool_name: str,
        success: bool,
        result: Any,
        arguments: Dict[str, Any],
    ) -> str:
        """Build a structured string for tool responses."""
        return format_tool_result(tool_name, success, result, arguments)

    # Execute tool function from registry with error handling and async support
    async def _execute_tool(self, tool_name: str, arguments: Dict) -> Tuple[bool, Any]:
        """Execute a tool. Returns (success, result)."""
        tool_func = self.tool_registry.get(tool_name)
        if not tool_func:
            return False, {"error": f"Unknown tool: {tool_name}"}

        try:
            # Call the function - it might be sync or async
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**arguments)
            else:
                result = tool_func(**arguments)

            # If the result is awaitable (like a coroutine), await it
            if inspect.isawaitable(result):
                result = await result

            return True, result
        except (ValueError, KeyError, TypeError) as e:
            # Handle expected parameter errors
            return False, {"error": f"Invalid parameters: {str(e)}"}
        except ToolExecutionError as e:
            # Handle tool-specific errors
            return False, {"error": str(e)}

    def _log_tool_invocation(
        self,
        tool_name: str,
        *,
        stage: str,
        arguments: Optional[Dict[str, Any]] = None,
        result: Optional[Any] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit structured logs for tool lifecycle events."""

        log_payload: Dict[str, Any] = {
            "tool": tool_name,
            "stage": stage,
            "agent": self.agent.name,
        }

        if arguments is not None:
            log_payload["arguments"] = arguments

        if result is not None:
            log_payload["result"] = result

        if detail:
            log_payload.update(detail)

        if stage == "done":
            logger.info(f"[{self.agent.name}] Tool '{tool_name}' completed")
        elif stage in {"error", "rejected"}:
            logger.warning(f"[{self.agent.name}] Tool '{tool_name}' {stage}")
        else:
            logger.debug(f"[{self.agent.name}] Tool '{tool_name}' {stage}")