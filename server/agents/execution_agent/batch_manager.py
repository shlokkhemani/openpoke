"""Coordinate execution agents and batch their results for the interaction agent."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .runtime import ExecutionAgentRuntime, ExecutionResult
from ...logging_config import logger
from ...config import get_settings
from ...openrouter_client import request_chat_completion
from ...services.agents.descriptions import DescriptionUpdater
from ...services.agents import indexer
from ...services.agents.store import get_agent_store
from ...services.triggers import get_trigger_service


@dataclass
class PendingExecution:
    """Track a pending execution request."""

    request_id: str
    agent_id: str
    instructions: str
    batch_id: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class _BatchState:
    """Collect results for a single interaction-agent turn."""

    batch_id: str
    created_at: datetime = field(default_factory=datetime.now)
    pending: int = 0
    results: List[ExecutionResult] = field(default_factory=list)


class ExecutionBatchManager:
    """Run execution agents and deliver their combined outcome."""

    # Initialize batch manager with timeout and coordination state for execution agents
    def __init__(self, timeout_seconds: int = 90, description_updater: Optional[Any] = None) -> None:
        self.timeout_seconds = timeout_seconds
        self._description_updater = description_updater
        self._description_tasks: set = set()
        self._pending: Dict[str, PendingExecution] = {}
        self._batch_lock = asyncio.Lock()
        self._batch_state: Optional[_BatchState] = None

    # Run execution agent (by id) with timeout handling and batch coordination for interaction agent
    async def execute_agent(
        self,
        agent_id: str,
        instructions: str,
        request_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute an agent asynchronously and buffer the result for batch dispatch."""

        if not request_id:
            request_id = str(uuid.uuid4())

        batch_id = await self._register_pending_execution(agent_id, instructions, request_id)

        agent_name = agent_id
        record = None

        try:
            record = get_agent_store().get(agent_id)
            if record is None:
                logger.error(f"[{agent_id}] Unknown agent id; execution skipped")
                result = ExecutionResult(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    success=False,
                    response=f"Execution failed: unknown agent id {agent_id}",
                    error=f"Unknown agent id: {agent_id}",
                )
            else:
                agent_name = record.name
                logger.info(f"[{agent_id}] Execution started")
                runtime = ExecutionAgentRuntime(agent_id)
                result = await asyncio.wait_for(
                    runtime.execute(instructions),
                    timeout=self.timeout_seconds,
                )
                status = "SUCCESS" if result.success else "FAILED"
                logger.info(f"[{agent_id}] Execution finished: {status}")
        except asyncio.TimeoutError:
            logger.error(f"[{agent_id}] Execution timed out after {self.timeout_seconds}s")
            result = ExecutionResult(
                agent_id=agent_id,
                agent_name=agent_name,
                success=False,
                response=f"Execution timed out after {self.timeout_seconds} seconds",
                error="Timeout",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(f"[{agent_id}] Execution failed unexpectedly")
            result = ExecutionResult(
                agent_id=agent_id,
                agent_name=agent_name,
                success=False,
                response=f"Execution failed: {exc}",
                error=str(exc),
            )
        finally:
            self._pending.pop(request_id, None)

        if record is not None:
            # Index every run: the description updater refreshes after a success; otherwise do it here.
            updating = result.success and self._schedule_description_update(agent_id, instructions, result)
            if not updating:
                self._refresh_search_index(agent_id)

        await self._complete_execution(batch_id, result, agent_id)
        return result

    # Build the production updater lazily: Settings.description_model, real LLM, triggers keyed by agent id
    def _get_description_updater(self) -> Any:
        if self._description_updater is None:
            settings = get_settings()

            async def llm(**kwargs: Any) -> Dict[str, Any]:
                return await request_chat_completion(api_key=settings.openrouter_api_key, **kwargs)

            self._description_updater = DescriptionUpdater(
                get_agent_store(),
                llm,
                settings.description_model,
                triggers=lambda agent_id: get_trigger_service().list_triggers(agent_id=agent_id),
                index=lambda agent_id, triggers=None: indexer.index_agent(agent_id, triggers),
            )
        return self._description_updater

    # Fire-and-forget description rewrite after a successful run; never blocks or fails the result
    def _schedule_description_update(self, agent_id: str, instructions: str, result: ExecutionResult) -> bool:
        """Schedule the rewrite; False when no updater could be built."""
        try:
            updater = self._get_description_updater()
        except Exception as exc:
            logger.warning(f"[{agent_id}] description updater unavailable: {exc}")
            return False

        async def run() -> None:
            try:
                await updater.update(agent_id, instructions, result.response, result.facts)
            except Exception as exc:
                logger.warning(f"[{agent_id}] description update failed: {exc}")

        task = asyncio.get_running_loop().create_task(run())
        self._description_tasks.add(task)
        task.add_done_callback(self._description_tasks.discard)
        return True

    # Rebuild the agent's search text after a run without a description update; never raises
    def _refresh_search_index(self, agent_id: str) -> None:
        try:
            indexer.index_agent(agent_id)
        except Exception as exc:
            logger.warning(f"[{agent_id}] search index refresh failed: {exc}")

    # Await all scheduled description updates (used by tests and shutdown)
    async def drain_description_updates(self) -> None:
        while self._description_tasks:
            await asyncio.gather(*list(self._description_tasks), return_exceptions=True)

    # Add execution request to current batch or create new batch if none exists
    async def _register_pending_execution(
        self,
        agent_id: str,
        instructions: str,
        request_id: str,
    ) -> str:
        """Attach a new execution to the active batch, opening one when required."""

        async with self._batch_lock:
            if self._batch_state is None:
                batch_id = str(uuid.uuid4())
                self._batch_state = _BatchState(batch_id=batch_id)
            else:
                batch_id = self._batch_state.batch_id

            self._batch_state.pending += 1
            self._pending[request_id] = PendingExecution(
                request_id=request_id,
                agent_id=agent_id,
                instructions=instructions,
                batch_id=batch_id,
            )

            return batch_id

    # Store execution result and send combined batch to interaction agent when complete
    async def _complete_execution(
        self,
        batch_id: str,
        result: ExecutionResult,
        agent_id: str,
    ) -> None:
        """Record the execution result and dispatch when the batch drains."""

        dispatch_payload: Optional[str] = None

        async with self._batch_lock:
            state = self._batch_state
            if state is None or state.batch_id != batch_id:
                logger.warning(f"[{agent_id}] Dropping result for unknown batch")
                return

            state.results.append(result)
            state.pending -= 1

            if state.pending == 0:
                dispatch_payload = self._format_batch_payload(state.results)
                agent_names = [entry.agent_name for entry in state.results]
                logger.info(f"Execution batch completed: {', '.join(agent_names)}")
                self._batch_state = None

        if dispatch_payload:
            await self._dispatch_to_interaction_agent(dispatch_payload)

    # Return list of currently pending execution requests for monitoring purposes
    def get_pending_executions(self) -> List[Dict[str, str]]:
        """Expose pending executions for observability."""

        return [
            {
                "request_id": pending.request_id,
                "agent_id": pending.agent_id,
                "batch_id": pending.batch_id,
                "created_at": pending.created_at.isoformat(),
                "elapsed_seconds": (datetime.now() - pending.created_at).total_seconds(),
            }
            for pending in self._pending.values()
        ]

    # Clean up all pending executions and batch state on shutdown
    async def shutdown(self) -> None:
        """Clear pending bookkeeping (no background work remains)."""

        self._pending.clear()
        await self.drain_description_updates()
        async with self._batch_lock:
            self._batch_state = None

    # Format multiple execution results into single message for interaction agent
    def _format_batch_payload(self, results: List[ExecutionResult]) -> str:
        """Render execution results into the interaction-agent format."""

        entries: List[str] = []
        for result in results:
            status = "SUCCESS" if result.success else "FAILED"
            response_text = (result.response or "(no response provided)").strip()
            entries.append(f"[{status}] {result.agent_name} (agent_id={result.agent_id}): {response_text}")
        return "\n".join(entries)

    # Forward combined execution results to interaction agent for user response generation
    async def _dispatch_to_interaction_agent(self, payload: str) -> None:
        """Send the aggregated execution summary to the interaction agent."""

        from ..interaction_agent.runtime import InteractionAgentRuntime

        runtime = InteractionAgentRuntime()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(runtime.handle_agent_message(payload))
            return

        loop.create_task(runtime.handle_agent_message(payload))
