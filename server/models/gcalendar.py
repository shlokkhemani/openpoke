"""Google Calendar models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CalendarConnectPayload(BaseModel):
    """Payload for initiating calendar connection."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: Optional[str] = Field(default=None, alias="user_id")
    auth_config_id: Optional[str] = Field(default=None, alias="auth_config_id")


class CalendarStatusPayload(BaseModel):
    """Payload for checking calendar connection status."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: Optional[str] = Field(default=None, alias="user_id")
    connection_request_id: Optional[str] = Field(default=None, alias="connection_request_id")


class CalendarDisconnectPayload(BaseModel):
    """Payload for disconnecting calendar."""
    model_config = ConfigDict(populate_by_name=True)

    user_id: Optional[str] = Field(default=None, alias="user_id")
    connection_id: Optional[str] = Field(default=None, alias="connection_id")
    connection_request_id: Optional[str] = Field(default=None, alias="connection_request_id")
