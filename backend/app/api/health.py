from __future__ import annotations

from fastapi import APIRouter

from ..config import settings

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "github_configured": bool(settings.github_token and settings.github_org),
    }
