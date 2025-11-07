from __future__ import annotations

import json
import threading
from typing import Any, Optional

from ..config import Settings, get_settings
from ..logging_config import logger

_CLIENT_LOCK = threading.Lock()
_CLIENT: Optional[Any] = None


def _import_composio():
    from composio import Composio  # type: ignore

    return Composio


def get_composio_client(settings: Optional[Settings] = None) -> Any:
    """Return a shared Composio client instance."""

    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    with _CLIENT_LOCK:
        if _CLIENT is None:
            resolved_settings = settings or get_settings()
            Composio = _import_composio()
            api_key = resolved_settings.composio_api_key
            try:
                _CLIENT = Composio(api_key=api_key) if api_key else Composio()
            except TypeError as exc:
                if api_key:
                    raise RuntimeError(
                        "Installed Composio SDK does not accept the api_key argument; upgrade the SDK or remove COMPOSIO_API_KEY."
                    ) from exc
                _CLIENT = Composio()
            logger.info("Composio client initialized")

    return _CLIENT


def normalize_composio_payload(result: Any) -> dict[str, Any]:
    """Convert Composio SDK responses into plain dictionaries."""

    payload_dict: Optional[dict[str, Any]] = None
    try:
        if hasattr(result, "model_dump"):
            payload_dict = result.model_dump()  # type: ignore[assignment]
        elif hasattr(result, "dict"):
            payload_dict = result.dict()  # type: ignore[assignment]
    except Exception:
        payload_dict = None

    if payload_dict is None:
        try:
            if hasattr(result, "model_dump_json"):
                payload_dict = json.loads(result.model_dump_json())
        except Exception:
            payload_dict = None

    if payload_dict is None:
        if isinstance(result, dict):
            payload_dict = result
        elif isinstance(result, list):
            payload_dict = {"items": result}
        else:
            payload_dict = {"repr": str(result)}

    return payload_dict


__all__ = [
    "get_composio_client",
    "normalize_composio_payload",
]
