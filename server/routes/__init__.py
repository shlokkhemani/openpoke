from __future__ import annotations

from fastapi import APIRouter

# DISABLED: Web chat interface - TELEGRAM ONLY
# from .chat import router as chat_router
from .data_admin import router as data_admin_router
from .gcalendar import router as calendar_router
from .gmail import router as gmail_router
from .lessons import router as lessons_router
from .meta import router as meta_router
from .profile import router as profile_router
from .telegram import router as telegram_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(meta_router)
# DISABLED: api_router.include_router(chat_router)  # WEB CHAT DISABLED - USE TELEGRAM
api_router.include_router(gmail_router)
api_router.include_router(calendar_router)
api_router.include_router(profile_router)
api_router.include_router(telegram_router)
api_router.include_router(data_admin_router)  # Railway Volume data management
api_router.include_router(lessons_router)  # Lessons learned management

__all__ = ["api_router"]
