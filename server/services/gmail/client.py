from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import status
from fastapi.responses import JSONResponse

from ...config import Settings
from ...logging_config import logger
from ...models import GmailConnectPayload, GmailDisconnectPayload, GmailStatusPayload
from ...utils import error_response
from ..composio_client import (
    get_composio_client as _shared_get_composio_client,
    normalize_composio_payload,
)

# PostgreSQL database imports
try:
    from ...database import SessionLocal
    from ...db_models import User
    _USE_DATABASE = True
except ImportError:
    _USE_DATABASE = False
    logger.warning("Database not available for Gmail persistence")


_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}
_PROFILE_CACHE_LOCK = threading.Lock()
_ACTIVE_USER_ID_LOCK = threading.Lock()
_ACTIVE_USER_ID: Optional[str] = None


def _normalized(value: Optional[str]) -> str:
    return (value or "").strip()


def _set_active_gmail_user_id(user_id: Optional[str]) -> None:
    sanitized = _normalized(user_id)
    with _ACTIVE_USER_ID_LOCK:
        global _ACTIVE_USER_ID
        _ACTIVE_USER_ID = sanitized or None


def get_active_gmail_user_id() -> Optional[str]:
    with _ACTIVE_USER_ID_LOCK:
        return _ACTIVE_USER_ID


def _get_composio_client(settings: Optional[Settings] = None):
    return _shared_get_composio_client(settings)


def _extract_email(obj: Any) -> Optional[str]:
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
    if isinstance(obj, dict):
        email_addresses = obj.get("emailAddresses")
        if isinstance(email_addresses, (list, tuple)):
            for entry in email_addresses:
                if isinstance(entry, dict):
                    candidate = entry.get("value") or entry.get("email") or entry.get("emailAddress")
                    if isinstance(candidate, str) and "@" in candidate:
                        return candidate
                elif isinstance(entry, str) and "@" in entry:
                    return entry
    if isinstance(obj, dict):
        nested_paths = (
            ("profile", "email"),
            ("profile", "emailAddress"),
            ("user", "email"),
            ("data", "email"),
            ("data", "user", "email"),
            ("provider_profile", "email"),
        )
        for path in nested_paths:
            current: Any = obj
            for segment in path:
                if isinstance(current, dict) and segment in current:
                    current = current[segment]
                else:
                    current = None
                    break
            if isinstance(current, str) and "@" in current:
                return current
    return None


def _save_gmail_to_db(connected: bool, email: Optional[str], connection_id: Optional[str]) -> None:
    """Save Gmail connection status to PostgreSQL database."""
    if not _USE_DATABASE:
        return

    try:
        db = SessionLocal()
        try:
            # Get or create user with ID=1 (single-user mode)
            user = db.query(User).filter(User.id == 1).first()
            if not user:
                user = User(id=1)
                db.add(user)

            # Update Gmail fields
            user.gmail_connected = connected
            user.gmail_email = email if connected else None
            user.gmail_connection_id = connection_id if connected else None

            db.commit()
            logger.info(f"💾 Gmail status saved to PostgreSQL: connected={connected}, email={email}")
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"❌ Failed to save Gmail status to database: {exc}")


def _load_gmail_from_db() -> Dict[str, Any]:
    """Load Gmail connection status from PostgreSQL database."""
    if not _USE_DATABASE:
        return {"connected": False, "email": None, "connection_id": None}

    try:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == 1).first()
            if user:
                return {
                    "connected": user.gmail_connected or False,
                    "email": user.gmail_email,
                    "connection_id": user.gmail_connection_id,
                }
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"❌ Failed to load Gmail status from database: {exc}")

    return {"connected": False, "email": None, "connection_id": None}


def _cache_profile(user_id: str, profile: Dict[str, Any]) -> None:
    sanitized = _normalized(user_id)
    if not sanitized or not isinstance(profile, dict):
        return
    with _PROFILE_CACHE_LOCK:
        _PROFILE_CACHE[sanitized] = {
            "profile": profile,
            "cached_at": datetime.utcnow().isoformat(),
        }


def _get_cached_profile(user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    sanitized = _normalized(user_id)
    if not sanitized:
        return None
    with _PROFILE_CACHE_LOCK:
        payload = _PROFILE_CACHE.get(sanitized)
        if payload and isinstance(payload.get("profile"), dict):
            return payload["profile"]
    return None


def _clear_cached_profile(user_id: Optional[str] = None) -> None:
    with _PROFILE_CACHE_LOCK:
        if user_id:
            _PROFILE_CACHE.pop(_normalized(user_id), None)
        else:
            _PROFILE_CACHE.clear()


def _fetch_profile_from_composio(user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    sanitized = _normalized(user_id)
    if not sanitized:
        return None
    try:
        result = execute_gmail_tool("GMAIL_GET_PROFILE", sanitized, arguments={"user_id": "me"})
    except RuntimeError as exc:
        logger.warning("GMAIL_GET_PROFILE invocation failed: %s", exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error fetching Gmail profile", extra={"user_id": sanitized})
        return None

    profile: Optional[Dict[str, Any]] = None
    if isinstance(result, dict):
        if isinstance(result.get("data"), dict):
            profile = result["data"]
        elif isinstance(result.get("profile"), dict):
            profile = result["profile"]
        elif isinstance(result.get("response_data"), dict):
            profile = result["response_data"]
        elif isinstance(result.get("items"), list):
            for item in result["items"]:
                if not isinstance(item, dict):
                    continue
                data_dict = item.get("data")
                if isinstance(data_dict, dict):
                    if isinstance(data_dict.get("response_data"), dict):
                        profile = data_dict["response_data"]
                    elif isinstance(data_dict.get("profile"), dict):
                        profile = data_dict["profile"]
                    else:
                        profile = data_dict
                elif isinstance(item.get("response_data"), dict):
                    profile = item["response_data"]
                elif isinstance(item.get("profile"), dict):
                    profile = item["profile"]
                if isinstance(profile, dict):
                    break
        elif result.get("successful") is True and isinstance(result.get("result"), dict):
            profile = result.get("result")  # type: ignore[assignment]
        elif all(not isinstance(result.get(key), dict) for key in ("data", "profile", "result")):
            profile = result if result else None

    if isinstance(profile, dict):
        _cache_profile(sanitized, profile)
        return profile

    logger.warning("Received unexpected Gmail profile payload", extra={"user_id": sanitized, "raw": result})
    return None


# Start Gmail OAuth connection process and return redirect URL
def initiate_connect(payload: GmailConnectPayload, settings: Settings) -> JSONResponse:
    auth_config_id = payload.auth_config_id or settings.composio_gmail_auth_config_id or ""
    if not auth_config_id:
        return error_response(
            "Missing auth_config_id. Set COMPOSIO_GMAIL_AUTH_CONFIG_ID or pass auth_config_id.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user_id = payload.user_id or f"web-{os.getpid()}"
    _set_active_gmail_user_id(user_id)
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
        logger.exception("gmail connect failed", extra={"user_id": user_id})
        return error_response(
            "Failed to initiate Gmail connect",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


# Check Gmail connection status and retrieve user account information
def fetch_status(payload: GmailStatusPayload) -> JSONResponse:
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
                    user_ids=[user_id], toolkit_slugs=["GMAIL"], statuses=["ACTIVE"]
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
        connected = False
        profile: Optional[Dict[str, Any]] = None
        profile_source = "none"

        account_user_id = None
        if account is not None:
            status_value = getattr(account, "status", None) or (account.get("status") if isinstance(account, dict) else None)
            normalized_status = (status_value or "").upper()
            connected = normalized_status in {"CONNECTED", "SUCCESS", "SUCCESSFUL", "ACTIVE", "COMPLETED"}
            email = _extract_email(account)
            if hasattr(account, "user_id"):
                account_user_id = getattr(account, "user_id", None)
            elif isinstance(account, dict):
                account_user_id = account.get("user_id")

        if not user_id and account_user_id:
            user_id = _normalized(account_user_id)

        if connected and user_id:
            cached_profile = _get_cached_profile(user_id)
            if cached_profile:
                profile = cached_profile
                profile_source = "cache"
            else:
                fetched_profile = _fetch_profile_from_composio(user_id)
                if fetched_profile:
                    profile = fetched_profile
                    profile_source = "fetched"
            if profile and not email:
                email = _extract_email(profile)
        elif user_id:
            _clear_cached_profile(user_id)

        _set_active_gmail_user_id(user_id)

        # Save Gmail connection status to PostgreSQL
        _save_gmail_to_db(connected, email, connection_request_id)

        return JSONResponse(
            {
                "ok": True,
                "connected": bool(connected),
                "status": status_value or "UNKNOWN",
                "email": email,
                "user_id": user_id,
                "profile": profile,
                "profile_source": profile_source,
            }
        )
    except Exception as exc:
        logger.exception(
            "gmail status failed",
            extra={
                "connection_request_id": connection_request_id,
                "user_id": user_id,
            },
        )
        return error_response(
            "Failed to fetch connection status",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


def disconnect_account(payload: GmailDisconnectPayload) -> JSONResponse:
    connection_id = _normalized(payload.connection_id) or _normalized(payload.connection_request_id)
    user_id = _normalized(payload.user_id)

    if not connection_id and not user_id:
        return error_response(
            "Missing connection_id or user_id",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        client = _get_composio_client()
    except Exception as exc:
        logger.exception("gmail disconnect failed: client init", extra={"user_id": user_id})
        return error_response(
            "Failed to disconnect Gmail",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    removed_ids: list[str] = []
    errors: list[str] = []
    affected_user_ids: set[str] = set()

    def _delete_connection(identifier: str) -> None:
        sanitized_id = _normalized(identifier)
        if not sanitized_id:
            return
        try:
            connection = client.connected_accounts.get(sanitized_id)
        except Exception:
            connection = None
        try:
            client.connected_accounts.delete(sanitized_id)
            removed_ids.append(sanitized_id)
            if connection is not None:
                if hasattr(connection, "user_id"):
                    affected_user_ids.add(_normalized(getattr(connection, "user_id", None)))
                elif isinstance(connection, dict):
                    affected_user_ids.add(_normalized(connection.get("user_id")))
        except Exception as exc:  # pragma: no cover - depends on remote state
            logger.exception("Failed to remove Gmail connection", extra={"connection_id": sanitized_id})
            errors.append(str(exc))

    if connection_id:
        _delete_connection(connection_id)
    else:
        try:
            items = client.connected_accounts.list(user_ids=[user_id], toolkit_slugs=["GMAIL"])
            data = getattr(items, "data", None)
            if data is None and isinstance(items, dict):
                data = items.get("data")
        except Exception as exc:  # pragma: no cover - dependent on SDK
            logger.exception("Failed to list Gmail connections", extra={"user_id": user_id})
            return error_response(
                "Failed to disconnect Gmail",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            )

        if data:
            for entry in data:
                candidate = None
                candidate_user_id = None
                if hasattr(entry, "id"):
                    candidate = getattr(entry, "id", None)
                    candidate_user_id = getattr(entry, "user_id", None)
                if candidate is None and isinstance(entry, dict):
                    candidate = entry.get("id")
                    candidate_user_id = entry.get("user_id")
                if candidate:
                    if candidate_user_id:
                        affected_user_ids.add(_normalized(candidate_user_id))
                    _delete_connection(candidate)

    if user_id:
        affected_user_ids.add(user_id)

    for uid in list(affected_user_ids):
        if uid:
            _clear_cached_profile(uid)
            if get_active_gmail_user_id() == uid:
                _set_active_gmail_user_id(None)

    if errors and not removed_ids:
        return error_response(
            "Failed to disconnect Gmail",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="; ".join(errors),
        )

    # Clear Gmail connection status from PostgreSQL
    if removed_ids:
        _save_gmail_to_db(False, None, None)

    response_payload = {
        "ok": True,
        "disconnected": bool(removed_ids),
        "removed_connection_ids": removed_ids,
    }
    if not removed_ids:
        response_payload["message"] = "No Gmail connection found"

    if errors:
        response_payload["warnings"] = errors
    return JSONResponse(response_payload)

# Execute Gmail operations through Composio SDK with error handling
def execute_gmail_tool(
    tool_name: str,
    composio_user_id: str,
    *,
    arguments: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    prepared_arguments: Dict[str, Any] = {}
    if isinstance(arguments, dict):
        for key, value in arguments.items():
            if value is not None:
                prepared_arguments[key] = value

    prepared_arguments.setdefault("user_id", "me")

    try:
        client = _get_composio_client()
        result = client.client.tools.execute(
            tool_name,
            user_id=composio_user_id,
            arguments=prepared_arguments,
        )
        return normalize_composio_payload(result)
    except Exception as exc:
        error_msg = str(exc)
        # Check for specific Composio connection errors
        if "No connected account found" in error_msg or "400" in error_msg:
            logger.warning(
                "Gmail tool execution failed - no connected account: %s",
                error_msg,
                extra={"tool": tool_name, "user_id": composio_user_id},
            )
            raise RuntimeError(f"Gmail not connected. Please connect your Gmail account first.") from exc
        else:
            logger.exception(
                "gmail tool execution failed",
                extra={"tool": tool_name, "user_id": composio_user_id},
            )
            raise RuntimeError(f"{tool_name} invocation failed: {exc}") from exc
