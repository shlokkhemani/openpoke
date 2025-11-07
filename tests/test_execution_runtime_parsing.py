from server.agents.execution_agent.runtime import ExecutionAgentRuntime


def _extract(runtime: ExecutionAgentRuntime, raw_tool_calls):
    return ExecutionAgentRuntime._extract_tool_calls(runtime, raw_tool_calls)


def test_execution_runtime_detects_concatenated_tools():
    runtime = object.__new__(ExecutionAgentRuntime)
    raw_tool_calls = [
        {
            "id": "x1",
            "function": {
                "name": "gmail_create_draftcalendar_create_event",
                "arguments": "{}",
            },
        }
    ]

    parsed = _extract(runtime, raw_tool_calls)
    assert len(parsed) == 1
    first = parsed[0]
    # Should use the first valid tool name and include invalid arguments marker
    assert first["name"] == "gmail_create_draft"
    assert "__invalid_arguments__" in first["arguments"]


def test_execution_runtime_accepts_valid_tool():
    runtime = object.__new__(ExecutionAgentRuntime)
    raw_tool_calls = [
        {
            "id": "x2",
            "function": {
                "name": "calendar_create_event",
                "arguments": '{"summary": "sync", "start_time": "2025-11-04T10:00:00Z", "end_time": "2025-11-04T11:00:00Z"}',
            },
        }
    ]

    parsed = _extract(runtime, raw_tool_calls)
    assert len(parsed) == 1
    first = parsed[0]
    assert first["name"] == "calendar_create_event"
    assert first["arguments"]["summary"] == "sync"


