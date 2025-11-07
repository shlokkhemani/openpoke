from server.agents.interaction_agent.runtime import InteractionAgentRuntime


def _parse(runtime: InteractionAgentRuntime, raw_tool_calls):
    # Bypass __init__ to avoid external dependencies (API keys, services)
    return InteractionAgentRuntime._parse_tool_calls(runtime, raw_tool_calls)


def test_interaction_runtime_detects_concatenated_tools():
    runtime = object.__new__(InteractionAgentRuntime)
    raw_tool_calls = [
        {
            "id": "test-1",
            "function": {
                "name": "send_message_to_usersend_draft",
                "arguments": "{}",
            },
        }
    ]

    parsed = _parse(runtime, raw_tool_calls)
    assert len(parsed) == 1
    # Should coerce to first valid tool name and mark invalid arguments
    first = parsed[0]
    assert getattr(first, "name") == "send_message_to_user"
    assert "__invalid_arguments__" in getattr(first, "arguments")


def test_interaction_runtime_accepts_valid_tool():
    runtime = object.__new__(InteractionAgentRuntime)
    raw_tool_calls = [
        {
            "id": "test-2",
            "function": {
                "name": "send_message_to_user",
                "arguments": '{"message": "hi"}',
            },
        }
    ]

    parsed = _parse(runtime, raw_tool_calls)
    assert len(parsed) == 1
    first = parsed[0]
    assert getattr(first, "name") == "send_message_to_user"
    assert getattr(first, "arguments").get("message") == "hi"


