from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import settings
from .auth import require_auth

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "github_configured": bool(settings.github_token and settings.github_org),
        "auth_required": bool(settings.admin_password),
    }


@router.post("/auth/check", dependencies=[Depends(require_auth)])
def auth_check() -> dict:
    """Verify a bearer token. Returns 200 if valid (or auth disabled), 401 otherwise.
    The frontend calls this after the user enters a password to confirm before saving it."""
    return {"ok": True}
