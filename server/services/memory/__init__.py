"""Long-term memory subsystem (LTM). Additive and flag-gated; nothing here runs when the flags are off."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .models import MemoryScope

if TYPE_CHECKING:  # pragma: no cover
    from .service import MemoryService

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "memory"

_service: "Optional[MemoryService]" = None
_service_lock = threading.Lock()


def resolve_memory_scope() -> MemoryScope:
    """The single scope seam (§23). PROTOTYPE: one local user. PRODUCTION: the authenticated principal only."""
    return MemoryScope(user_id=os.getenv("OPENPOKE_LTM_USER", "local-user"))


def get_memory_service() -> "MemoryService":
    """Process-wide service, built lazily from settings. Only called when ``ltm_enabled``."""
    global _service
    with _service_lock:
        if _service is None:
            from ...config import get_settings
            from .service import MemoryService
            from .store import MemoryStore

            settings = get_settings()
            store = MemoryStore(DATA_DIR / "ltm.db")
            _service = MemoryService(
                store,
                extractor=_build_extractor(settings),
                debug_events=bool(getattr(settings, "ltm_debug_events", False)),
                test_hooks=bool(getattr(settings, "ltm_test_hooks", False)),
            )
        return _service


def _build_extractor(settings):
    from .extractor import RuleExtractor

    if getattr(settings, "ltm_extractor", "rules") == "llm":
        from .extractor import LLMExtractor

        return LLMExtractor(model=getattr(settings, "memory_extractor_model", None) or settings.summarizer_model)
    return RuleExtractor()


def reset_memory_service() -> None:
    """Drop the singleton (tests, restart simulation)."""
    global _service
    with _service_lock:
        _service = None


__all__ = ["MemoryScope", "resolve_memory_scope", "get_memory_service", "reset_memory_service"]
