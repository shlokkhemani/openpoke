"""LTM debug + test-hook endpoints (design §17.1, D26, handoff C1/C2/C14).

Mounted only when ``OPENPOKE_LTM_DEBUG=1``; every request is re-checked and must come from loopback, because the
server binds 0.0.0.0 with no auth (F-1). Test hooks additionally need ``OPENPOKE_LTM_TEST_HOOKS=1``.
Outputs are sanitised and pass the trace leak guard.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config import get_settings

router = APIRouter(prefix="/memory/debug", tags=["memory-debug"])

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _guard(request: Request, *, hooks: bool = False) -> None:
    settings = get_settings()
    if not settings.ltm_enabled or not settings.ltm_debug or (hooks and not settings.ltm_test_hooks):
        raise HTTPException(status_code=404, detail="Not Found")
    host = request.client.host if request.client else None
    if host not in _LOOPBACK:
        raise HTTPException(status_code=403, detail="Forbidden")


def _service():
    from ..services.memory import get_memory_service

    return get_memory_service()


@router.get("/traces")
def traces(request: Request, limit: int = 20) -> Any:
    """C1: newest first ``[{trace_id, ts, source_kind, kind, turn_id}]``."""
    _guard(request)
    return _service().list_traces(limit=limit)


@router.get("/trace/{trace_id}")
def trace(trace_id: str, request: Request) -> Dict[str, Any]:
    _guard(request)
    from ..services.memory import resolve_memory_scope
    from ..services.memory.trace import assemble_turn_trace

    return assemble_turn_trace(_service().sink, resolve_memory_scope(), trace_id)


@router.get("/state")
def state(request: Request) -> Dict[str, Any]:
    _guard(request)
    from ..services.memory import resolve_memory_scope
    from ..services.memory.trace import memory_state_snapshot

    svc = _service()
    return memory_state_snapshot(svc.store, svc.sink, resolve_memory_scope())


class IngestDelayRequest(BaseModel):
    duplicate_next_job_with_delay_ms: int


class AwaitIdleRequest(BaseModel):
    timeout_s: float = 10.0
    include_delayed: bool = True


@router.post("/test/ingest-delay")
def ingest_delay(payload: IngestDelayRequest, request: Request) -> Dict[str, Any]:
    """C14: the next ingest job is enqueued twice; the copy (same TurnRef) sleeps before taking the user lock."""
    _guard(request, hooks=True)
    _service().set_duplicate_next_job(payload.duplicate_next_job_with_delay_ms)
    return {"ok": True, "duplicate_next_job_with_delay_ms": payload.duplicate_next_job_with_delay_ms}


@router.post("/test/await-idle")
async def await_idle(request: Request, payload: Optional[AwaitIdleRequest] = None) -> Any:
    """C2: returns once every ingest job (incl. delayed duplicates unless excluded) committed or fence-dropped."""
    _guard(request, hooks=True)
    payload = payload or AwaitIdleRequest()
    svc = _service()
    idle = await svc.await_idle(timeout=min(payload.timeout_s, 10.0), include_delayed=payload.include_delayed)
    body = {"idle": idle, "pending": svc.pending(payload.include_delayed)}
    return body if idle else JSONResponse(body, status_code=504)


__all__ = ["router"]
