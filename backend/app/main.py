from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, health, metrics, sync, teams
from .config import settings
from .scheduler import start as start_scheduler
from .scheduler import stop as stop_scheduler
from .sources import seed_from_env_vars

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One-time idempotent seed: convert env-var credentials into data_sources rows so the
    # UI can manage them. Safe to run on every boot — only inserts when no matching row.
    try:
        seed_from_env_vars()
    except Exception:  # noqa: BLE001
        logging.exception("Failed to seed data_sources from env vars (continuing)")
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"https://.*\.vercel\.app",  # any Vercel preview deploy
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(sync.router)
app.include_router(teams.router)
app.include_router(admin.router)
