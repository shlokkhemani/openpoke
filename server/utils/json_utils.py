"""JSON utility functions for safe serialization and parsing."""

import json
from typing import Any, Dict, Optional, Tuple


def safe_json_dump(payload: Any) -> str:
    """
    Safely serialize a payload to JSON string.

    Falls back to string representation if JSON serialization fails.
    Uses str() as the default handler for non-serializable objects.

    Args:
        payload: The object to serialize to JSON

    Returns:
        JSON string representation of the payload, or str() representation
        if serialization fails

    Examples:
        >>> safe_json_dump({"key": "value"})
        '{"key": "value"}'
        >>> safe_json_dump({"date": datetime.now()})
        '{"date": "2025-11-04 12:00:00"}'
    """
    try:
        return json.dumps(payload, default=str)
    except TypeError:
        return repr(payload)


def safe_json_load(raw_data: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Safely parse JSON data into a dictionary.

    Handles multiple input formats (dict, JSON string, None) and returns
    a tuple of (parsed_dict, error_message). If parsing succeeds, error
    is None. If parsing fails, returns empty dict and error message.

    Args:
        raw_data: The data to parse - can be dict, JSON string, or None

    Returns:
        Tuple of (parsed_dict, error_message). Error is None on success.

    Examples:
        >>> safe_json_load('{"key": "value"}')
        ({"key": "value"}, None)
        >>> safe_json_load({"key": "value"})
        ({"key": "value"}, None)
        >>> safe_json_load("invalid json")
        ({}, "invalid json: Expecting value: line 1 column 1 (char 0)")
    """
    if raw_data is None:
        return {}, None

    if isinstance(raw_data, dict):
        return raw_data, None

    if isinstance(raw_data, str):
        if not raw_data.strip():
            return {}, None
        try:
            parsed = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            return {}, f"invalid json: {exc}"
        if isinstance(parsed, dict):
            return parsed, None
        return {}, "decoded arguments were not an object"

    return {}, f"unsupported argument type: {type(raw_data).__name__}"
