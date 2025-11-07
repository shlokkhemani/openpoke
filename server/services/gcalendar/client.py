"""Google Calendar client for Composio integration.

KNOWN ISSUE (2025-11-04):
    Composio's execute_action fails when calling GOOGLECALENDAR_LIST_CALENDARS
    after successful OAuth connection. This is a backend configuration bug on 
    Composio's side, not a permissions issue. The connection is valid but the
    execute_action endpoint crashes, preventing us from fetching calendar metadata.
    
    Workaround: We return connection success even without email/calendar list.
    TODO: Dev needs to check Composio backend config and API integration settings.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import status
from fastapi.responses import JSONResponse

from ...config import Settings
from ...logging_config import logger
from ...models import CalendarConnectPayload, CalendarDisconnectPayload, CalendarStatusPayload
from ...utils import error_response
from ..composio_client import (
    get_composio_client as _shared_get_composio_client,
    normalize_composio_payload,
)

_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}
_PROFILE_CACHE_LOCK = threading.Lock()
_ACTIVE_USER_ID_LOCK = threading.Lock()
_ACTIVE_USER_ID: Optional[str] = None


def _normalized(value: Optional[str]) -> str:
    """Normalize string values."""
    return (value or "").strip()


def _set_active_calendar_user_id(user_id: Optional[str]) -> None:
    """Set the active calendar user ID."""
    sanitized = _normalized(user_id)
    with _ACTIVE_USER_ID_LOCK:
        global _ACTIVE_USER_ID
        _ACTIVE_USER_ID = sanitized or None


def get_active_calendar_user_id() -> Optional[str]:
    """Get the active calendar user ID."""
    with _ACTIVE_USER_ID_LOCK:
        return _ACTIVE_USER_ID


def _get_composio_client(settings: Optional[Settings] = None):
    """Get shared Composio client."""
    return _shared_get_composio_client(settings)


def _extract_email(obj: Any) -> Optional[str]:
    """Extract email from various object structures."""
    if obj is None:
        return None
    
    direct_keys = (
        "email",
        "email_address",
        "emailAddress",
        "user_email",
        "provider_email",
        "account_email",
    )
    
    for key in direct_keys:
        try:
            val = getattr(obj, key)
            if isinstance(val, str) and "@" in val:
                return val
        except Exception:
            pass
        if isinstance(obj, dict):
            val = obj.get(key)
            if isinstance(val, str) and "@" in val:
                return val
    
    return None


def _cache_profile(user_id: str, profile: Dict[str, Any]) -> None:
    """Cache calendar profile data."""
    sanitized = _normalized(user_id)
    if not sanitized or not isinstance(profile, dict):
        return
    with _PROFILE_CACHE_LOCK:
        _PROFILE_CACHE[sanitized] = {
            "profile": profile,
            "cached_at": datetime.utcnow().isoformat(),
        }


def _get_cached_profile(user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Retrieve cached calendar profile."""
    sanitized = _normalized(user_id)
    if not sanitized:
        return None
    with _PROFILE_CACHE_LOCK:
        payload = _PROFILE_CACHE.get(sanitized)
        if payload and isinstance(payload.get("profile"), dict):
            return payload["profile"]
    return None


def _clear_cached_profile(user_id: Optional[str] = None) -> None:
    """Clear cached calendar profile."""
    with _PROFILE_CACHE_LOCK:
        if user_id:
            _PROFILE_CACHE.pop(_normalized(user_id), None)
        else:
            _PROFILE_CACHE.clear()


def execute_calendar_tool(
    tool_name: str,
    user_id: Optional[str] = None,
    *,
    arguments: Optional[Dict[str, Any]] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Execute a Google Calendar tool via Composio.
    
    Args:
        tool_name: Name of the calendar tool (e.g., GOOGLECALENDAR_CREATE_EVENT)
        user_id: Optional Composio user ID
        arguments: Tool arguments
        settings: Optional settings override
        
    Returns:
        Tool execution result as dictionary
    """
    sanitized_user_id = _normalized(user_id) or get_active_calendar_user_id()
    
    if not sanitized_user_id:
        logger.warning("No calendar user_id provided and no active user configured")
        return {"error": "Calendar account not connected"}
    
    # Prepare arguments, filtering out None values
    prepared_arguments: Dict[str, Any] = {}
    if isinstance(arguments, dict):
        for key, value in arguments.items():
            if value is not None:
                prepared_arguments[key] = value
    
    try:
        client = _get_composio_client(settings)
        
        logger.info(
            f"Executing calendar tool: {tool_name} for user: {sanitized_user_id}",
            extra={
                "tool": tool_name,
                "user_id": sanitized_user_id,
                "arguments": prepared_arguments
            }
        )
        
        # Use client.client.tools.execute() like Gmail does
        result = client.client.tools.execute(
            tool_name,
            user_id=sanitized_user_id,
            arguments=prepared_arguments,
        )
        
        normalized = normalize_composio_payload(result)
        
        logger.info(f"Calendar tool {tool_name} executed successfully")
        return normalized
        
    except Exception as exc:
        error_msg = str(exc)
        # Check for specific Composio connection errors
        if "No connected account found" in error_msg or "400" in error_msg or "OAuth" in error_msg or "authentication" in error_msg.lower():
            logger.error(
                "Calendar tool execution failed - authentication/connection issue",
                extra={
                    "tool": tool_name,
                    "user_id": sanitized_user_id,
                    "error": error_msg,
                    "suggestion": "User may need to reconnect their Calendar account or token may be expired"
                }
            )
            return {"error": f"Calendar authentication required. Please reconnect your Calendar account. Details: {error_msg}"}
        else:
            logger.exception(
                f"Calendar tool execution failed: {tool_name}",
                extra={"tool": tool_name, "user_id": sanitized_user_id, "error": str(exc)}
            )
            return {"error": f"Failed to execute calendar tool: {str(exc)}"}


def initiate_calendar_connect(
    payload: CalendarConnectPayload, settings: Settings
) -> JSONResponse:
    """
    Initiate Google Calendar OAuth connection flow.
    
    Args:
        payload: Connection payload with user_id and auth_config_id
        settings: Settings instance
        
    Returns:
        JSON response with redirect URL or error
    """
    import os
    import uuid
    
    auth_config_id = payload.auth_config_id or settings.composio_calendar_auth_config_id or ""
    if not auth_config_id:
        logger.error(
            "COMPOSIO_CALENDAR_AUTH_CONFIG_ID not configured",
            extra={
                "required_env": "COMPOSIO_CALENDAR_AUTH_CONFIG_ID",
                "solution": "Set this environment variable with your Composio Calendar auth config ID"
            }
        )
        return error_response(
            "Calendar integration not configured. Missing COMPOSIO_CALENDAR_AUTH_CONFIG_ID environment variable. "
            "Please contact your administrator to set up the Calendar integration.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Use provided user_id or generate a stable one
    user_id = payload.user_id or f"web-{uuid.uuid4().hex}"
    
    logger.info(f"Initiating Calendar connect for user: {user_id}")
    
    _set_active_calendar_user_id(user_id)
    _clear_cached_profile(user_id)
    
    try:
        client = _get_composio_client(settings)
        req = client.connected_accounts.initiate(user_id=user_id, auth_config_id=auth_config_id)
        data = {
            "ok": True,
            "redirect_url": getattr(req, "redirect_url", None) or getattr(req, "redirectUrl", None),
            "connection_request_id": getattr(req, "id", None),
            "user_id": user_id,
        }
        return JSONResponse(data)
    except Exception as exc:
        logger.exception("calendar connect failed", extra={"user_id": user_id})
        return error_response(
            "Failed to initiate Calendar connect",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


def _fetch_calendar_info(user_id: str) -> Optional[str]:
    """
    Fetch calendar information to get user email.
    
    Args:
        user_id: Composio user ID
        
    Returns:
        Email address if found, None otherwise
    """
    try:
        # Try to get calendar list to extract email
        # NOTE: This may fail due to Composio execute_action bug
        result = execute_calendar_tool(
            "GOOGLECALENDAR_LIST_CALENDARS",
            user_id,
            arguments={}
        )
        
        # Check if there's an error in the result
        if isinstance(result, dict) and result.get("error"):
            logger.error(
                f"Composio execute_action error when fetching calendar list: {result.get('error')}",
                extra={
                    "user_id": user_id,
                    "tool": "GOOGLECALENDAR_LIST_CALENDARS",
                    "composio_bug": "execute_action failure - backend config issue"
                }
            )
            return None
        
        if isinstance(result, dict):
            # Look for email in various possible locations
            calendars = result.get("items") or result.get("data") or result.get("calendars")
            if isinstance(calendars, list) and len(calendars) > 0:
                primary_calendar = calendars[0]
                if isinstance(primary_calendar, dict):
                    email = (
                        primary_calendar.get("id") or
                        primary_calendar.get("email") or
                        primary_calendar.get("summary")
                    )
                    if email and "@" in email:
                        return email
            
            # Check top-level fields
            email = _extract_email(result)
            if email:
                return email
                
    except Exception as exc:
        logger.error(
            f"Exception while fetching calendar info - likely Composio backend bug: {exc}",
            extra={
                "user_id": user_id,
                "error_type": type(exc).__name__,
                "composio_bug": "execute_action failure - needs backend config review"
            }
        )
    
    return None


def fetch_calendar_status(
    payload: CalendarStatusPayload
) -> JSONResponse:
    """
    Fetch Google Calendar connection status.
    
    Args:
        payload: Status payload with connection_request_id or user_id
        
    Returns:
        JSON response with connection status
    """
    connection_request_id = _normalized(payload.connection_request_id)
    user_id = _normalized(payload.user_id)

    if not connection_request_id and not user_id:
        return error_response(
            "Missing connection_request_id or user_id",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        client = _get_composio_client()
        account: Any = None
        
        if connection_request_id:
            try:
                account = client.connected_accounts.wait_for_connection(connection_request_id, timeout=2.0)
            except Exception:
                try:
                    account = client.connected_accounts.get(connection_request_id)
                except Exception:
                    account = None
                    
        if account is None and user_id:
            try:
                items = client.connected_accounts.list(
                    user_ids=[user_id], toolkit_slugs=["GOOGLECALENDAR"], statuses=["ACTIVE"]
                )
                data = getattr(items, "data", None)
                if data is None and isinstance(items, dict):
                    data = items.get("data")
                if data:
                    account = data[0]
            except Exception:
                account = None
                
        status_value = None
        email = None
        
        if account:
            status_value = getattr(account, "status", None)
            email = _extract_email(account)
            
            # If we have an active connection but no email, try to fetch calendar info
            if status_value and status_value.upper() == "ACTIVE" and not email and user_id:
                email = _fetch_calendar_info(user_id)
            
            if status_value and status_value.upper() == "ACTIVE":
                if user_id:
                    _set_active_calendar_user_id(user_id)
                    if email:
                        _cache_profile(user_id, {"email": email})
                
                # Return connected status even if email fetch failed (Composio bug workaround)
                return JSONResponse({
                    "ok": True,
                    "status": "active",
                    "email": email or "Connected (email unavailable - Composio execute_action bug)",
                    "connection_request_id": connection_request_id,
                    "user_id": user_id,
                    "warning": None if email else "Calendar connected but unable to fetch email due to Composio backend issue"
                })
                
        return JSONResponse({
            "ok": False,
            "status": status_value or "not_connected",
            "email": None,
            "connection_request_id": connection_request_id,
            "user_id": user_id,
        })
        
    except Exception as exc:
        logger.exception("calendar status check failed")
        return error_response(
            "Failed to check calendar status",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


def disconnect_calendar_account(
    payload: CalendarDisconnectPayload
) -> JSONResponse:
    """
    Disconnect Google Calendar account.
    
    Args:
        payload: Disconnect payload with user_id and optional connection_id
        
    Returns:
        JSON response confirming disconnection
    """
    user_id = _normalized(payload.user_id)
    connection_id = _normalized(payload.connection_id)
    connection_request_id = _normalized(payload.connection_request_id)

    if not user_id and not connection_id and not connection_request_id:
        return error_response(
            "Missing user_id, connection_id, or connection_request_id",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        client = _get_composio_client()
        
        # If we have connection_id, delete it directly
        if connection_id:
            client.connected_accounts.delete(connection_id)
        # Otherwise, find and delete by user_id
        elif user_id:
            try:
                items = client.connected_accounts.list(
                    user_ids=[user_id], toolkit_slugs=["GOOGLECALENDAR"]
                )
                data = getattr(items, "data", None)
                if data is None and isinstance(items, dict):
                    data = items.get("data")
                if data:
                    for account in data:
                        acc_id = getattr(account, "id", None)
                        if acc_id:
                            client.connected_accounts.delete(acc_id)
            except Exception as exc:
                logger.warning(f"Failed to find/delete calendar accounts for user: {user_id}", extra={"error": str(exc)})
        
        # Clear cache
        if user_id:
            _clear_cached_profile(user_id)
            if get_active_calendar_user_id() == user_id:
                _set_active_calendar_user_id(None)
        
        return JSONResponse({
            "ok": True,
            "message": "Calendar disconnected",
            "user_id": user_id,
        })
        
    except Exception as exc:
        logger.exception("calendar disconnect failed")
        return error_response(
            "Failed to disconnect calendar",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
