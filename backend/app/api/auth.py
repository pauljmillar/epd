"""Optional password gate.

If ADMIN_PASSWORD is set, all routers that depend on `require_auth` reject requests without
`Authorization: Bearer <ADMIN_PASSWORD>`. If unset, the dependency is a no-op — appropriate
for local dev and the public demo on the OSS repo.

This is intentionally simple (not OAuth, not SSO) per BRD §17.
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from ..config import settings


def require_auth(authorization: str | None = Header(default=None)) -> None:
    pw = settings.admin_password
    if not pw:
        return  # auth disabled
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(token, pw):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
