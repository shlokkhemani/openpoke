from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings

from .chat import router as chat_router
from .gmail import router as gmail_router
from .meta import router as meta_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(meta_router)
api_router.include_router(chat_router)
api_router.include_router(gmail_router)

if get_settings().ltm_debug:  # LTM debug + test-hook routes: flag-gated and loopback-only (D26)
    from .memory_debug import router as memory_debug_router

    api_router.include_router(memory_debug_router)

__all__ = ["api_router"]
