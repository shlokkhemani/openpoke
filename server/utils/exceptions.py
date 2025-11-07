"""Custom exception classes for domain-specific error handling.

This module provides a hierarchy of exceptions that allow for precise error
handling across the codebase, avoiding overly broad exception catching while
maintaining clear error semantics.
"""


class OpenPokeError(Exception):
    """Base exception for all OpenPoke-specific errors.

    This should be the base class for all custom exceptions in the codebase.
    It allows catching all application errors while letting system exceptions
    (SystemExit, KeyboardInterrupt, etc.) propagate naturally.
    """
    pass


class AgentExecutionError(OpenPokeError):
    """Raised when an agent fails to execute properly.

    This covers errors in the agent execution lifecycle, including:
    - LLM call failures
    - Invalid agent responses
    - Agent iteration limit exceeded
    - Agent state corruption

    Attributes:
        agent_name: Name of the agent that failed
        details: Additional context about the failure
    """

    def __init__(self, message: str, agent_name: str = None, details: dict = None):
        super().__init__(message)
        self.agent_name = agent_name
        self.details = details or {}


class ToolExecutionError(OpenPokeError):
    """Raised when a tool execution fails.

    This covers errors during tool invocation, including:
    - Invalid tool arguments
    - Tool not found
    - Tool execution crashes
    - Tool timeout

    Attributes:
        tool_name: Name of the tool that failed
        arguments: Arguments passed to the tool
        original_error: The underlying exception if any
    """

    def __init__(self, message: str, tool_name: str = None, arguments: dict = None, original_error: Exception = None):
        super().__init__(message)
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.original_error = original_error


class ConfigurationError(OpenPokeError):
    """Raised when there's a configuration issue.

    This covers:
    - Missing required configuration values
    - Invalid configuration values
    - Configuration file access issues

    Attributes:
        config_key: The configuration key that caused the issue
    """

    def __init__(self, message: str, config_key: str = None):
        super().__init__(message)
        self.config_key = config_key


class TriggerSchedulingError(OpenPokeError):
    """Raised when trigger scheduling or execution fails.

    This covers:
    - Invalid trigger configuration
    - Trigger execution failures
    - Schedule parsing errors

    Attributes:
        trigger_id: ID of the trigger that failed
        agent_name: Name of the agent associated with the trigger
    """

    def __init__(self, message: str, trigger_id: int = None, agent_name: str = None):
        super().__init__(message)
        self.trigger_id = trigger_id
        self.agent_name = agent_name


class ConversationLogError(OpenPokeError):
    """Raised when conversation log operations fail.

    This covers:
    - File I/O failures
    - Parse errors
    - Encoding issues

    Attributes:
        operation: The operation that failed (read, write, parse, etc.)
    """

    def __init__(self, message: str, operation: str = None):
        super().__init__(message)
        self.operation = operation


__all__ = [
    "OpenPokeError",
    "AgentExecutionError",
    "ToolExecutionError",
    "ConfigurationError",
    "TriggerSchedulingError",
    "ConversationLogError",
]
