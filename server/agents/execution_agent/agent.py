"""Execution Agent implementation."""

from pathlib import Path
from typing import List, Optional, Dict, Any

from ...services.execution import get_execution_agent_logs
from ...logging_config import logger
from .tools import get_tool_schemas


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

    # Initialize execution agent with name, conversation limits, and log store access
    def __init__(
        self,
        name: str,
        conversation_limit: Optional[int] = None
    ):
        """
        Initialize an execution agent.

        Args:
            name: Human-readable agent name (e.g., 'conversation with keith')
            conversation_limit: Optional limit on past conversations to include (None = all)
        """
        self.name = name
        self.conversation_limit = conversation_limit
        self._log_store = get_execution_agent_logs()

    def _generate_available_tools_section(self) -> str:
        """
        Dynamically generate the Available Tools section based on registered tools.
        
        Returns:
            Formatted markdown section listing all available tools with descriptions.
        """
        tool_schemas = get_tool_schemas()
        
        # Group tools by category
        gmail_tools = []
        google_super_tools = []
        search_tools = []
        trigger_tools = []
        task_tools = []
        
        for schema in tool_schemas:
            func = schema.get("function", {})
            name = func.get("name", "")
            description = func.get("description", "")
            
            if name.startswith("gmail_"):
                gmail_tools.append(f"- {name} — {description}")
            elif name.startswith("googlesuper"):
                google_super_tools.append(f"- {name} — {description}")
            elif name.startswith("search_") or name == "research_topic":
                search_tools.append(f"- {name} — {description}")
            elif name.endswith("Trigger") or "trigger" in name.lower():
                trigger_tools.append(f"- {name} — {description}")
            else:
                task_tools.append(f"- {name} — {description}")
        
        sections = []
        
        if gmail_tools:
            sections.append("**Gmail Tools**\n" + "\n".join(gmail_tools))
        
        if google_super_tools:
            sections.append("**Google Super Tools (via Composio)**\n" + "\n".join(google_super_tools))
        
        if search_tools:
            sections.append("**Search Tools**\n" + "\n".join(search_tools))
        
        if trigger_tools:
            sections.append("**Reminder & Trigger Tools**\n" + "\n".join(trigger_tools))
        
        if task_tools:
            sections.append("**Advanced Task Tools**\n" + "\n".join(task_tools))
        
        return "# Available Tools\n\n" + "\n\n".join(sections)

    # Generate system prompt template with agent name and purpose derived from name
    def build_system_prompt(self) -> str:
        """Build the system prompt for this agent."""
        agent_purpose = f"Handle tasks related to: {self.name}"
        
        # Generate dynamic tools section
        tools_section = self._generate_available_tools_section()
        
        # Load base prompt and replace the Available Tools section
        base_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            agent_name=self.name,
            agent_purpose=agent_purpose
        )
        
        # Add specific instructions for reminder agents
        instructions_section = self._get_agent_specific_instructions()
        
        # Replace the instructions placeholder
        if "[TO BE FILLED IN BY USER - Add your specific instructions here]" in base_prompt:
            base_prompt = base_prompt.replace(
                "[TO BE FILLED IN BY USER - Add your specific instructions here]",
                instructions_section
            )
        
        # Replace the static Available Tools section with dynamic one
        if "# Available Tools" in base_prompt:
            # Find the start and end of the Available Tools section
            start_marker = "# Available Tools"
            end_marker = "# Guidelines"
            
            start_idx = base_prompt.find(start_marker)
            end_idx = base_prompt.find(end_marker)
            
            if start_idx != -1 and end_idx != -1:
                base_prompt = (
                    base_prompt[:start_idx] +
                    tools_section + "\n\n" +
                    base_prompt[end_idx:]
                )

        return base_prompt

    def _get_agent_specific_instructions(self) -> str:
        """Get agent-specific instructions based on the agent name."""
        agent_name_lower = self.name.lower()
        
        # Special instructions for reminder agents
        if "rappel" in agent_name_lower or "remind" in agent_name_lower or "reminder" in agent_name_lower:
            return """When you receive a trigger firing notification with reminder content in the payload:
1. Simply acknowledge the reminder by returning the payload text as your final response
2. Do not try to create new triggers, use tools, or perform any other actions
3. Your response should be the reminder text that will be shown to the user
4. Keep your response clear and concise - just the reminder content

Example: If the payload is "Rappel: Réunion équipe à 14h", respond with "Rappel: Réunion équipe à 14h"."""
        
        # Default instructions for other agents
        return """Follow the user's instructions carefully. Use available tools when needed to complete tasks. Provide clear, helpful responses."""

    # Combine base system prompt with conversation history, applying conversation limits
    def build_system_prompt_with_history(self) -> str:
        """
        Build system prompt including agent history.

        Returns:
            System prompt with embedded history transcript
        """
        base_prompt = self.build_system_prompt()

        # Load history transcript
        transcript = self._log_store.load_transcript(self.name)

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
        self._log_store.record_agent_response(self.name, response)

    # Log tool invocation and results with truncated content for readability
    def record_tool_execution(self, tool_name: str, arguments: str, result: str) -> None:
        """Record tool execution details."""
        self._log_store.record_action(self.name, f"Calling {tool_name} with: {arguments[:200]}")
        # Record the tool response
        self._log_store.record_tool_response(self.name, tool_name, result[:500])
