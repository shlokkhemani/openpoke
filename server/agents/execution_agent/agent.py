"""Execution Agent implementation."""

from pathlib import Path
from typing import List, Optional, Dict, Any

from ...services.agents.store import AgentStore, get_agent_store
from ...services.execution import get_execution_agent_logs
from ...logging_config import logger


# Load system prompt template from file
_prompt_path = Path(__file__).parent / "system_prompt.md"
if _prompt_path.exists():
    SYSTEM_PROMPT_TEMPLATE = _prompt_path.read_text(encoding="utf-8").strip()
else:
    # Placeholder template - you'll replace this with actual instructions
    SYSTEM_PROMPT_TEMPLATE = """You are an execution agent responsible for completing specific tasks using available tools.

Agent Name: {agent_name}
Purpose: {agent_purpose}

Instructions:
[TO BE FILLED IN BY USER]

You have access to Gmail tools to help complete your tasks. When given instructions:
1. Analyze what needs to be done
2. Use the appropriate tools to complete the task
3. Provide clear status updates on your actions

Be thorough, accurate, and efficient in your execution."""


class ExecutionAgent:
    """Manages state and history for an execution agent."""

    # Initialize execution agent by id, resolving its name and description from the agent store
    def __init__(
        self,
        agent_id: str,
        conversation_limit: Optional[int] = None,
        store: Optional[AgentStore] = None,
    ):
        """
        Initialize an execution agent.

        Args:
            agent_id: Agent id in the agent store (e.g. 'ag_abcd2345'); logs are keyed by it
            conversation_limit: Optional limit on past conversations to include (None = all)
            store: Agent store to resolve the agent from (defaults to the global store)
        """
        self.agent_id = agent_id
        self._store = store if store is not None else get_agent_store()
        record = self._store.get(agent_id)
        if record is None:
            raise ValueError(f"Unknown agent id: {agent_id}")
        self.name = record.name
        self.description = record.description
        self.conversation_limit = conversation_limit
        self._log_store = get_execution_agent_logs()

    # Generate system prompt with the stored agent name and description
    def build_system_prompt(self) -> str:
        """Build the system prompt for this agent."""
        agent_purpose = self.description or f"Handle tasks related to: {self.name}"

        return SYSTEM_PROMPT_TEMPLATE.format(
            agent_name=self.name,
            agent_purpose=agent_purpose
        )

    # Combine base system prompt with conversation history, applying conversation limits
    def build_system_prompt_with_history(self) -> str:
        """
        Build system prompt including agent history.

        Returns:
            System prompt with embedded history transcript
        """
        base_prompt = self.build_system_prompt()

        # Load history transcript
        transcript = self._log_store.load_transcript(self.agent_id)

        if transcript:
            # Apply conversation limit if needed
            if self.conversation_limit and self.conversation_limit > 0:
                # Parse entries and limit them
                lines = transcript.split('\n')
                request_count = sum(1 for line in lines if '<agent_request' in line)

                if request_count > self.conversation_limit:
                    # Find where to cut
                    kept_requests = 0
                    cutoff_index = len(lines)
                    for i in range(len(lines) - 1, -1, -1):
                        if '<agent_request' in lines[i]:
                            kept_requests += 1
                            if kept_requests == self.conversation_limit:
                                cutoff_index = i
                                break
                    transcript = '\n'.join(lines[cutoff_index:])

            return f"{base_prompt}\n\n# Execution History\n\n{transcript}"

        return base_prompt

    # Format current instruction as user message for LLM consumption
    def build_messages_for_llm(self, current_instruction: str) -> List[Dict[str, str]]:
        """
        Build message array for LLM call.

        Args:
            current_instruction: Current instruction from interaction agent

        Returns:
            List of messages in OpenRouter format
        """
        return [
            {"role": "user", "content": current_instruction}
        ]

    # Log the agent's final response to the execution log store
    def record_response(self, response: str) -> None:
        """Record agent's response to the log."""
        self._log_store.record_agent_response(self.agent_id, response)

    # Log tool invocation and results with truncated content for readability
    def record_tool_execution(self, tool_name: str, arguments: str, result: str) -> None:
        """Record tool execution details."""
        self._log_store.record_action(self.agent_id, f"Calling {tool_name} with: {arguments[:200]}")
        # Record the tool response
        self._log_store.record_tool_response(self.agent_id, tool_name, result[:500])
