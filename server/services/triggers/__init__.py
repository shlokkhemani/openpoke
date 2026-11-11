from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from .models import TriggerRecord
from .service import TriggerService
from .store import TriggerStore


_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_default_db_path = _DATA_DIR / "triggers.db"
_trigger_service: Optional[TriggerService] = None
_service_lock = threading.Lock()


def get_trigger_service() -> TriggerService:
    """Build the default service on first use so importing never opens (or migrates) the real DB."""
    global _trigger_service
    if _trigger_service is None:
        with _service_lock:
            if _trigger_service is None:
                _trigger_service = TriggerService(TriggerStore(_default_db_path))
    return _trigger_service


__all__ = [
    "TriggerRecord",
    "TriggerService",
    "get_trigger_service",
]
