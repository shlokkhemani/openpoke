#!/usr/bin/env python3
"""
Script to apply error handling improvements to all files.
This script makes all changes atomically to avoid conflicts with file watchers.

Usage:
    python3 apply_error_handling.py [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def update_interaction_agent(content: str) -> Tuple[str, List[str]]:
    """Update interaction agent runtime with improved error handling."""
    changes = []

    # Add import if not present
    if "from ...utils.exceptions import AgentExecutionError" not in content:
        import_line = "from ...logging_config import logger\n"
        new_import = "from ...logging_config import logger\nfrom ...utils.exceptions import AgentExecutionError, ToolExecutionError\n"
        content = content.replace(import_line, new_import)
        changes.append("Added exception imports")

    # Update first exception block (execute method)
    old_block_1 = '''        except Exception as exc:
            logger.error("Interaction agent failed", extra={"error": str(exc)})
            return InteractionResult(
                success=False,
                response="",
                error=str(exc),
            )'''

    new_block_1 = '''        except (ValueError, KeyError, TypeError) as exc:
            # Handle expected data validation errors
            logger.warning(
                "Interaction agent data validation error",
                extra={"error": str(exc), "error_type": type(exc).__name__}
            )
            return InteractionResult(
                success=False,
                response="",
                error=f"Invalid data: {str(exc)}",
            )
        except json.JSONDecodeError as exc:
            # Handle JSON parsing errors
            logger.warning(
                "Interaction agent JSON decode error",
                extra={"error": str(exc), "doc": exc.doc[:100] if hasattr(exc, 'doc') else None}
            )
            return InteractionResult(
                success=False,
                response="",
                error=f"JSON parsing failed: {str(exc)}",
            )
        except AgentExecutionError as exc:
            # Handle agent-specific errors
            logger.error(
                "Interaction agent execution failed",
                extra={"error": str(exc), "agent": exc.agent_name, "details": exc.details},
                exc_info=True
            )
            return InteractionResult(
                success=False,
                response="",
                error=str(exc),
            )
        except Exception as exc:
            # Handle unexpected errors with full logging
            logger.error(
                "Interaction agent unexpected error",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True
            )
            return InteractionResult(
                success=False,
                response="",
                error=f"Unexpected error: {str(exc)}",
            )'''

    if old_block_1 in content:
        content = content.replace(old_block_1, new_block_1)
        changes.append("Updated execute() exception handling")

    # Update second exception block (handle_agent_message method)
    old_block_2 = '''        except Exception as exc:
            logger.error("Interaction agent (agent message) failed", extra={"error": str(exc)})
            return InteractionResult(
                success=False,
                response="",
                error=str(exc),
            )'''

    new_block_2 = '''        except (ValueError, KeyError, TypeError) as exc:
            # Handle expected data validation errors
            logger.warning(
                "Interaction agent (agent message) data validation error",
                extra={"error": str(exc), "error_type": type(exc).__name__}
            )
            return InteractionResult(
                success=False,
                response="",
                error=f"Invalid data: {str(exc)}",
            )
        except json.JSONDecodeError as exc:
            # Handle JSON parsing errors
            logger.warning(
                "Interaction agent (agent message) JSON decode error",
                extra={"error": str(exc), "doc": exc.doc[:100] if hasattr(exc, 'doc') else None}
            )
            return InteractionResult(
                success=False,
                response="",
                error=f"JSON parsing failed: {str(exc)}",
            )
        except AgentExecutionError as exc:
            # Handle agent-specific errors
            logger.error(
                "Interaction agent (agent message) execution failed",
                extra={"error": str(exc), "agent": exc.agent_name, "details": exc.details},
                exc_info=True
            )
            return InteractionResult(
                success=False,
                response="",
                error=str(exc),
            )
        except Exception as exc:
            # Handle unexpected errors with full logging
            logger.error(
                "Interaction agent (agent message) unexpected error",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True
            )
            return InteractionResult(
                success=False,
                response="",
                error=f"Unexpected error: {str(exc)}",
            )'''

    if old_block_2 in content:
        content = content.replace(old_block_2, new_block_2)
        changes.append("Updated handle_agent_message() exception handling")

    return content, changes


def update_execution_agent(content: str) -> Tuple[str, List[str]]:
    """Update execution agent runtime with improved error handling."""
    changes = []

    # Import should already be present, but check
    if "from server.utils.exceptions import" not in content:
        print("WARNING: Expected imports not found in execution agent")

    # Update first exception block (execute method)
    old_block_1 = '''        except Exception as e:
            logger.error(f"[{self.agent.name}] Execution failed: {e}")
            error_msg = str(e)
            failure_text = f"Failed to complete task: {error_msg}"
            self.agent.record_response(f"Error: {error_msg}")

            return ExecutionResult(
                agent_name=self.agent.name,
                success=False,
                response=failure_text,
                error=error_msg
            )'''

    new_block_1 = '''        except (ValueError, KeyError, TypeError) as e:
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
        except Exception as e:
            # Handle unexpected errors with full logging
            logger.error(
                f"[{self.agent.name}] Unexpected execution error",
                extra={"error": str(e), "error_type": type(e).__name__},
                exc_info=True
            )
            error_msg = str(e)
            failure_text = f"Failed to complete task: {error_msg}"
            self.agent.record_response(f"Error: {error_msg}")

            return ExecutionResult(
                agent_name=self.agent.name,
                success=False,
                response=failure_text,
                error=error_msg
            )'''

    if old_block_1 in content:
        content = content.replace(old_block_1, new_block_1)
        changes.append("Updated execute() exception handling")

    # Update second exception block (_execute_tool method)
    old_block_2 = '''        except Exception as e:
            logger.error(f"[{self.agent.name}] Tool execution error: {e}", exc_info=True)
            return False, {"error": str(e)}'''

    new_block_2 = '''        except (ValueError, KeyError, TypeError) as e:
            # Handle expected parameter errors
            logger.warning(
                f"[{self.agent.name}] Tool parameter error: {tool_name}",
                extra={"error": str(e), "error_type": type(e).__name__, "arguments": arguments}
            )
            return False, {"error": f"Invalid parameters: {str(e)}"}
        except ToolExecutionError as e:
            # Handle tool-specific errors
            logger.error(
                f"[{self.agent.name}] Tool execution error: {tool_name}",
                extra={"error": str(e), "tool": e.tool_name, "arguments": e.arguments},
                exc_info=True
            )
            return False, {"error": str(e)}
        except Exception as e:
            # Handle unexpected tool errors
            logger.error(
                f"[{self.agent.name}] Unexpected tool error: {tool_name}",
                extra={"error": str(e), "error_type": type(e).__name__},
                exc_info=True
            )
            return False, {"error": str(e)}'''

    if old_block_2 in content:
        content = content.replace(old_block_2, new_block_2)
        changes.append("Updated _execute_tool() exception handling")

    return content, changes


def update_trigger_scheduler(content: str) -> Tuple[str, List[str]]:
    """Update trigger scheduler with improved error handling."""
    changes = []

    # Add import if not present
    if "from ..utils.exceptions import TriggerSchedulingError" not in content:
        import_line = "from ..logging_config import logger\n"
        new_import = "from ..logging_config import logger\nfrom ..utils.exceptions import TriggerSchedulingError\n"
        content = content.replace(import_line, new_import)
        changes.append("Added exception imports")

    # Note: The exception blocks in this file are more complex due to asyncio.CancelledError handling
    # Manual review recommended for these changes

    return content, changes


def update_conversation_log(content: str) -> Tuple[str, List[str]]:
    """Update conversation log with improved error handling."""
    changes = []

    # Add import if not present
    if "from ...utils.exceptions import ConversationLogError" not in content:
        import_line = "from ...logging_config import logger\n"
        new_import = "from ...logging_config import logger\nfrom ...utils.exceptions import ConversationLogError\n"
        content = content.replace(import_line, new_import)
        changes.append("Added exception imports")

    # Note: This file has many exception blocks, some intentionally broad
    # Manual review recommended for these changes

    return content, changes


def main():
    parser = argparse.ArgumentParser(description="Apply error handling improvements")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    args = parser.parse_args()

    files_to_update = {
        "server/agents/interaction_agent/runtime.py": update_interaction_agent,
        "server/agents/execution_agent/runtime.py": update_execution_agent,
        "server/services/trigger_scheduler.py": update_trigger_scheduler,
        "server/services/conversation/log.py": update_conversation_log,
    }

    print("Error Handling Improvement Script")
    print("=" * 60)
    print()

    for filepath, update_func in files_to_update.items():
        path = Path(filepath)
        if not path.exists():
            print(f"❌ {filepath}: File not found")
            continue

        print(f"Processing: {filepath}")

        # Read file
        content = path.read_text()

        # Apply updates
        updated_content, changes = update_func(content)

        if not changes:
            print(f"  ℹ️  No changes needed")
            continue

        # Show changes
        for change in changes:
            print(f"  ✓ {change}")

        # Write file if not dry-run
        if not args.dry_run:
            path.write_text(updated_content)
            print(f"  💾 File updated")
        else:
            print(f"  🔍 Dry-run: Changes not applied")

        print()

    if args.dry_run:
        print("\n🔍 Dry-run complete. Run without --dry-run to apply changes.")
    else:
        print("\n✅ All updates applied!")
        print("\nNext steps:")
        print("1. Review changes in trigger_scheduler.py and conversation/log.py")
        print("2. Run tests to verify error handling")
        print("3. Check logging output for proper error details")


if __name__ == "__main__":
    main()
