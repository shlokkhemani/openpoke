from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from ...config import Settings, get_settings
from ...logging_config import logger
from ..composio_client import get_composio_client, normalize_composio_payload

_DEFAULT_TOOLKIT_SLUG = "GOOGLESUPER"

_USER_ID_LOCK = threading.Lock()
_ACTIVE_USER_ID: Optional[str] = None

_ACCOUNT_ID_LOCK = threading.Lock()
_ACTIVE_CONNECTED_ACCOUNT_ID: Optional[str] = None


def _normalize(value: Optional[str]) -> str:
    return (value or "").strip()


def set_active_google_super_user_id(user_id: Optional[str]) -> None:
    sanitized = _normalize(user_id)
    with _USER_ID_LOCK:
        global _ACTIVE_USER_ID
        _ACTIVE_USER_ID = sanitized or None


def _set_connected_account_id(account_id: Optional[str]) -> None:
    sanitized = _normalize(account_id)
    with _ACCOUNT_ID_LOCK:
        global _ACTIVE_CONNECTED_ACCOUNT_ID
        _ACTIVE_CONNECTED_ACCOUNT_ID = sanitized or None


def get_connected_google_super_account_id(settings: Optional[Settings] = None) -> Optional[str]:
    resolved_settings = settings or get_settings()
    with _ACCOUNT_ID_LOCK:
        if _ACTIVE_CONNECTED_ACCOUNT_ID:
            return _ACTIVE_CONNECTED_ACCOUNT_ID

    fallback = _normalize(resolved_settings.composio_google_super_connected_account_id)
    if fallback:
        _set_connected_account_id(fallback)
        return fallback

    _autodiscover_connected_account(resolved_settings)
    with _ACCOUNT_ID_LOCK:
        return _ACTIVE_CONNECTED_ACCOUNT_ID


def _extract_attr(obj: Any, attr: str) -> Optional[str]:
    value: Any = None
    if hasattr(obj, attr):
        try:
            value = getattr(obj, attr)
        except Exception:
            value = None
    if isinstance(obj, dict) and value is None:
        value = obj.get(attr)
    if isinstance(value, str):
        sanitized = _normalize(value)
        return sanitized or None
    if value is not None:
        return str(value)
    return None


def _extract_list_candidates(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("data", "items", "results", "connected_accounts"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    for attr in ("data", "items", "results"):
        if hasattr(payload, attr):
            try:
                value = getattr(payload, attr)
            except Exception:
                value = None
            if isinstance(value, list):
                return value

    return []


def _autodiscover_connected_account(settings: Settings) -> None:
    try:
        client = get_composio_client(settings)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to initialize Composio client for Google Super", extra={"error": str(exc)})
        return

    toolkit_slug = get_google_super_toolkit_slug(settings)
    try:
        accounts = client.connected_accounts.list(
            toolkit_slugs=[toolkit_slug],
            statuses=["ACTIVE"],
        )
    except Exception as exc:  # pragma: no cover - depends on remote state
        logger.warning("Failed to list Google Super connected accounts", extra={"error": str(exc)})
        return

    normalized_accounts = normalize_composio_payload(accounts)
    for entry in _extract_list_candidates(normalized_accounts):
        user_id = _extract_attr(entry, "user_id")
        connection_id = _extract_attr(entry, "id")
        if user_id:
            set_active_google_super_user_id(user_id)
        if connection_id:
            _set_connected_account_id(connection_id)
        if user_id:
            break


def get_google_super_toolkit_slug(settings: Optional[Settings] = None) -> str:
    resolved_settings = settings or get_settings()
    slug = _normalize(resolved_settings.composio_google_super_toolkit_slug)
    return slug or _DEFAULT_TOOLKIT_SLUG


def _ensure_account_loaded(settings: Settings) -> None:
    existing_user = get_active_google_super_user_id(settings)
    if existing_user:
        return

    fallback_user = _normalize(settings.composio_google_super_user_id)
    if fallback_user:
        set_active_google_super_user_id(fallback_user)

    fallback_account = _normalize(settings.composio_google_super_connected_account_id)
    if fallback_account:
        _set_connected_account_id(fallback_account)

    if not fallback_user:
        _autodiscover_connected_account(settings)


def get_active_google_super_user_id(settings: Optional[Settings] = None) -> Optional[str]:
    resolved_settings = settings or get_settings()
    with _USER_ID_LOCK:
        if _ACTIVE_USER_ID:
            return _ACTIVE_USER_ID

    fallback = _normalize(resolved_settings.composio_google_super_user_id)
    if fallback:
        set_active_google_super_user_id(fallback)
        return fallback

    _autodiscover_connected_account(resolved_settings)
    with _USER_ID_LOCK:
        return _ACTIVE_USER_ID


def _simplify_tool_payload(tool: Any) -> Dict[str, Any]:
    payload = normalize_composio_payload(tool)

    simplified: Dict[str, Any] = {}
    for key in ("name", "tool_name", "slug", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            simplified["name"] = value
            break

    if "description" in payload:
        simplified["description"] = payload["description"]
    elif "summary" in payload:
        simplified["description"] = payload["summary"]

    for key in ("input_schema", "parameters", "schema", "args_schema", "inputSchema"):
        if key in payload:
            simplified["parameters"] = payload[key]
            break

    if "category" in payload:
        simplified["category"] = payload["category"]
    if "auth_schemes" in payload:
        simplified["auth_schemes"] = payload["auth_schemes"]

    simplified["raw"] = payload
    return simplified


def list_google_super_tools(
    *,
    search: Optional[str] = None,
    limit: Optional[int] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    resolved_settings = settings or get_settings()
    _ensure_account_loaded(resolved_settings)

    max_results = max(1, min(limit or 20, 50))
    toolkit_slug = get_google_super_toolkit_slug(resolved_settings)

    try:
        client = get_composio_client(resolved_settings)
        tools_client = getattr(getattr(client, "client", client), "tools", None)
        if tools_client is None:
            return {"error": "Composio tools API unavailable"}
        request_kwargs: Dict[str, Any] = {"toolkit_slugs": [toolkit_slug], "limit": max_results}
        if search:
            request_kwargs["search"] = search
        try:
            response = tools_client.list(**request_kwargs)
        except TypeError:
            response = tools_client.list()
    except Exception as exc:  # pragma: no cover - depends on remote state
        logger.exception("Failed to list Google Super tools", extra={"error": str(exc)})
        return {"error": str(exc)}

    normalized = normalize_composio_payload(response)
    entries = _extract_list_candidates(normalized)[:max_results]
    simplified = [_simplify_tool_payload(entry) for entry in entries]

    total_available = None
    for key in ("total", "total_count", "count", "totalResults"):
        value = normalized.get(key) if isinstance(normalized, dict) else None
        if isinstance(value, int):
            total_available = value
            break

    result: Dict[str, Any] = {
        "toolkit": toolkit_slug,
        "search": search,
        "returned": len(simplified),
        "tools": simplified,
    }
    if total_available is not None:
        result["total_available"] = total_available

    return result


def describe_google_super_tool(
    tool_name: str,
    *,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    if not _normalize(tool_name):
        return {"error": "tool_name is required"}

    resolved_settings = settings or get_settings()
    try:
        client = get_composio_client(resolved_settings)
        tools_client = getattr(getattr(client, "client", client), "tools", None)
        if tools_client is None:
            return {"error": "Composio tools API unavailable"}
        getter = getattr(tools_client, "get", None)
        if callable(getter):
            response = getter(tool_name)
        else:
            list_response = tools_client.list(toolkit_slugs=[get_google_super_toolkit_slug(resolved_settings)], search=tool_name)
            normalized = normalize_composio_payload(list_response)
            entries = _extract_list_candidates(normalized)
            response = entries[0] if entries else None
    except Exception as exc:  # pragma: no cover - depends on remote state
        logger.exception("Failed to fetch Google Super tool metadata", extra={"tool": tool_name, "error": str(exc)})
        return {"error": str(exc)}

    if response is None:
        return {"error": f"Tool {tool_name} not found"}

    simplified = _simplify_tool_payload(response)
    return {"tool": simplified}


def execute_google_super_tool(
    tool_name: str,
    *,
    arguments: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    sanitized_name = _normalize(tool_name)
    if not sanitized_name:
        return {"error": "tool_name is required"}

    resolved_settings = settings or get_settings()
    target_user_id = _normalize(user_id) or get_active_google_super_user_id(resolved_settings)
    if not target_user_id:
        return {"error": "Google Super not connected. Provide COMPOSIO_GOOGLESUPER_USER_ID or connect the toolkit in Composio."}

    prepared_arguments: Dict[str, Any] = {}
    if isinstance(arguments, dict):
        for key, value in arguments.items():
            if value is not None:
                prepared_arguments[key] = value

    try:
        client = get_composio_client(resolved_settings)
        tools_client = getattr(getattr(client, "client", client), "tools", None)
        if tools_client is None:
            return {"error": "Composio tools API unavailable"}
        result = tools_client.execute(
            sanitized_name,
            user_id=target_user_id,
            arguments=prepared_arguments,
        )
        return normalize_composio_payload(result)
    except Exception as exc:  # pragma: no cover - depends on remote state
        error_msg = str(exc)
        if "No connected account" in error_msg or "400" in error_msg:
            logger.warning(
                "Google Super tool execution failed - connection issue",
                extra={"tool": sanitized_name, "user_id": target_user_id, "error": error_msg},
            )
            return {"error": "Google Super account not connected. Reconnect in Composio."}
        logger.exception(
            "Google Super tool execution failed",
            extra={"tool": sanitized_name, "user_id": target_user_id},
        )
        return {"error": f"{sanitized_name} invocation failed: {exc}"}


__all__ = [
    "describe_google_super_tool",
    "execute_google_super_tool",
    "get_active_google_super_user_id",
    "get_connected_google_super_account_id",
    "get_google_super_toolkit_slug",
    "list_google_super_tools",
    "set_active_google_super_user_id",
]
