"""Google Calendar API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..models import CalendarConnectPayload, CalendarDisconnectPayload, CalendarStatusPayload
from ..services import disconnect_calendar_account, fetch_calendar_status, initiate_calendar_connect

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.post("/connect")
async def calendar_connect(
    payload: CalendarConnectPayload, settings: Settings = Depends(get_settings)
) -> JSONResponse:
    """Initiate Google Calendar OAuth connection flow through Composio."""
    return initiate_calendar_connect(payload, settings)


@router.post("/status")
async def calendar_status(payload: CalendarStatusPayload) -> JSONResponse:
    """Check the current Google Calendar connection status and user information."""
    return fetch_calendar_status(payload)


@router.post("/disconnect")
async def calendar_disconnect(payload: CalendarDisconnectPayload) -> JSONResponse:
    """Disconnect Google Calendar account and clear cached profile data."""
    return disconnect_calendar_account(payload)
