"""Read-only observability endpoints for isolated benchmark servers."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status

from ..agents.interaction_agent.tools import get_execution_batch_manager
from ..benchmark_clock import get_benchmark_clock
from ..config import Settings, get_settings
from ..data_paths import DEFAULT_DATA_DIR, get_data_dir
from ..services import (
    get_agent_roster,
    get_conversation_log,
    get_execution_agent_logs,
    get_trigger_service,
)
from ..services.benchmark_activity import get_interaction_activity
from ..services.conversation.summarization.scheduler import get_summarization_status
from ..services.gmail import benchmark_email_fixture_enabled
from ..services.gmail.client import _get_benchmark_backend
from ..benchmark_events import read_events


router = APIRouter(prefix="/benchmark", tags=["benchmark"])


def _require_benchmark_mode(settings: Settings) -> None:
    if not settings.benchmark_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _status_payload(settings: Settings) -> dict[str, object]:
    roster = get_agent_roster()
    roster.load()
    agents = roster.get_agents()
    pending = get_execution_batch_manager().get_pending_executions()
    active_interactions = get_interaction_activity().active_count()
    summarization = get_summarization_status()
    conversation_entries = list(get_conversation_log().iter_entries())
    data_dir = get_data_dir()
    return {
        "benchmark_mode": True,
        "isolated_tools": settings.benchmark_tools_isolated,
        "email_fixture_enabled": benchmark_email_fixture_enabled(),
        "data_dir": str(data_dir),
        "isolated_data_dir": data_dir != DEFAULT_DATA_DIR,
        "idle": (
            active_interactions == 0
            and not pending
            and not summarization["pending"]
            and not summarization["running"]
        ),
        "active_interactions": active_interactions,
        "interaction_failure_count": get_interaction_activity().failure_count(),
        "failures": get_interaction_activity().failures(),
        "pending_executions": pending,
        "summarization": summarization,
        "roster_size": len(agents),
        "roster_agents": agents,
        "conversation_entry_count": len(conversation_entries),
        "user_message_count": sum(
            entry[0] == "user_message" for entry in conversation_entries
        ),
        "simulated_day": get_benchmark_clock().day(),
    }


@router.get("/status")
def benchmark_status(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Return activity and roster state used by the setup runner."""
    _require_benchmark_mode(settings)
    return _status_payload(settings)


@router.get("/metrics")
def benchmark_metrics(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Preserve email-action evidence even when a failed group is not idle."""
    _require_benchmark_mode(settings)
    events = read_events()
    return {"metrics_events": events, "token_tracking_version": 1}


@router.get("/snapshot")
def benchmark_snapshot(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Return the naturally generated roster and histories for a run artifact."""
    _require_benchmark_mode(settings)
    status_payload = _status_payload(settings)
    if not status_payload["idle"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Benchmark server is still processing work",
        )

    roster_agents = list(status_payload["roster_agents"])
    logs = get_execution_agent_logs()
    execution_histories = {
        agent_name: [
            {"type": tag, "timestamp": timestamp, "content": payload}
            for tag, timestamp, payload in logs.iter_entries(agent_name)
        ]
        for agent_name in roster_agents
    }
    conversation = [
        {"type": tag, "timestamp": timestamp, "content": payload}
        for tag, timestamp, payload in get_conversation_log().iter_entries()
    ]
    triggers = [
        trigger.model_dump(mode="json")
        for trigger in get_trigger_service().list_all_triggers()
    ]
    events = read_events()
    return {
        "status": status_payload,
        "conversation": conversation,
        "execution_agent_histories": execution_histories,
        "triggers": triggers,
        "metrics_version": 1,
        "token_tracking_version": 1,
        "clock_time": get_benchmark_clock().now_utc().isoformat(),
        "metrics_events": events,
        "routing": {
            "mode": "shortlist" if settings.roster_shortlisting_enabled else "full_roster",
            "embedding_model": settings.roster_embedding_model,
            "percentage": settings.roster_match_percentage,
            "min_size": settings.roster_match_min_size,
            "max_size": settings.roster_match_max_size,
            "recent_tasks": settings.roster_match_recent_tasks,
        },
        "models": {name: getattr(settings, name) for name in (
            "interaction_agent_model", "execution_agent_model", "execution_agent_search_model",
            "summarizer_model", "email_classifier_model")},
        "email_state": (_get_benchmark_backend().snapshot()
                        if benchmark_email_fixture_enabled() else None),
    }


@router.post("/day")
def set_benchmark_day(
    day: int = Body(..., embed=True),
    settings: Settings = Depends(get_settings),
) -> dict[str, int]:
    """Advance the benchmark's logical clock without waiting in real time."""
    _require_benchmark_mode(settings)
    try:
        get_benchmark_clock().set_day(day)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {"day": get_benchmark_clock().day()}


@router.delete("/day")
def reset_benchmark_day(
    settings: Settings = Depends(get_settings),
) -> dict[str, int]:
    """Reset the logical clock before a fresh isolated setup run."""
    _require_benchmark_mode(settings)
    get_benchmark_clock().reset()
    get_interaction_activity().reset_failures()
    return {"day": 0}


__all__ = ["router"]
