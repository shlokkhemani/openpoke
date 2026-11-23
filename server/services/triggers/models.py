from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class TriggerRecord(BaseModel):
    """Serialized trigger representation returned to callers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    # Owning identity. For reminders this is the reserved reminder owner id.
    agent_name: str
    # Execution agent that created the trigger, preserved as provenance.
    created_by: Optional[str] = None
    # When true, every agent may see and manage this trigger.
    shared: bool = False
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
