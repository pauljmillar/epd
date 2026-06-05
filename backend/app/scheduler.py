from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from .db import session_scope
from .models import SyncLog
from .snapshots import finalize_prior_month
from .sync import run_sync_sync

log = logging.getLogger(__name__)

scheduler: BackgroundScheduler | None = None


def _has_any_sync() -> bool:
    with session_scope() as s:
        return s.execute(select(SyncLog.id).limit(1)).first() is not None


def start() -> None:
    global scheduler
    if scheduler is not None:
        return
    scheduler = BackgroundScheduler()

    # Nightly sync at 02:00 UTC
    scheduler.add_job(run_sync_sync, CronTrigger(hour=2, minute=0), id="nightly_sync")
    # Monthly finalization on the 1st at 06:00 UTC
    scheduler.add_job(
        finalize_prior_month, CronTrigger(day=1, hour=6, minute=0), id="finalize_month"
    )

    scheduler.start()
    log.info("Scheduler started")

    # First-run backfill
    if not _has_any_sync():
        log.info("No prior sync detected; scheduling initial backfill")
        scheduler.add_job(run_sync_sync, id="initial_backfill")


def stop() -> None:
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
