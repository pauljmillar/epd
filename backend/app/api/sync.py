from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

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
