from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import SyncLog
from ..snapshots import last_sync_status
from ..sync import run_sync
from .auth import require_auth

router = APIRouter(prefix="/api/v1/sync", tags=["sync"], dependencies=[Depends(require_auth)])

_trigger_lock = asyncio.Lock()
_last_triggered: float = 0.0

log = logging.getLogger(__name__)


@router.get("/status")
def status() -> dict:
    return last_sync_status()


@router.post("/trigger")
async def trigger() -> dict:
    import time

    global _last_triggered
    if _trigger_lock.locked():
        raise HTTPException(409, "Sync already running")
    if time.time() - _last_triggered < 3600:
        raise HTTPException(429, "Sync was triggered within the last hour")
    _last_triggered = time.time()
    async with _trigger_lock:
        result = await run_sync()
    return result


@router.post("/cancel")
def cancel(s: Session = Depends(get_session)) -> dict:
    """Flag the running sync to stop at the next safe boundary (between repos). The loop
    in sync.py will commit the in-flight repo, then exit cleanly with status='cancelled'."""
    running = s.execute(
        select(SyncLog).where(SyncLog.status == "running").order_by(SyncLog.started_at.desc())
    ).scalars().first()
    if not running:
        raise HTTPException(404, "No sync currently running")
    if running.cancel_requested:
        return {"ok": True, "already_requested": True, "sync_log_id": running.id}
    running.cancel_requested = True
    s.commit()
    return {"ok": True, "sync_log_id": running.id}
