from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class TriggerRecord(BaseModel):
    """Serialized trigger representation returned to callers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    payload: str
    start_time: Optional[str] = None
    next_trigger: Optional[str] = None
    recurrence_rule: Optional[str] = None
    timezone: Optional[str] = None
    status: str
    last_error: Optional[str] = None
    created_at: str
    updated_at: str


__all__ = ["TriggerRecord"]
