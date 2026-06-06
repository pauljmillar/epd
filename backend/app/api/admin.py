"""Admin endpoints for toggling is_tracked on repos and contributors.

Distinct from /metrics/repos and /metrics/contributors (which only return tracked rows for
the dashboard sidebar). Admin views return everything so the user can flip toggles.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Contributor, PullRequest, Repository
from .auth import require_auth
from .metrics import cache_invalidate_all

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_auth)])


class TrackedPatch(BaseModel):
    is_tracked: bool


@router.get("/repos")
def list_all_repos(s: Session = Depends(get_session)) -> dict:
    """Every known repo (tracked + untracked) with lifetime merged PR count."""
    rows = s.execute(
        select(
            Repository.full_name,
            Repository.is_tracked,
            func.count(PullRequest.id).label("prs"),
        )
        .outerjoin(
            PullRequest,
            (PullRequest.repo_id == Repository.id) & (PullRequest.merged_at.is_not(None)),
        )
        .group_by(Repository.full_name, Repository.is_tracked)
        .order_by(func.count(PullRequest.id).desc())
    ).all()
    return {
        "repos": [
            {"full_name": full, "is_tracked": bool(tracked), "prs_merged_total": int(prs)}
            for full, tracked, prs in rows
        ]
    }


@router.patch("/repos/{repo_full_name:path}")
def set_repo_tracked(
    repo_full_name: str,
    body: TrackedPatch,
    s: Session = Depends(get_session),
) -> dict:
    repo = s.execute(
        select(Repository).where(Repository.full_name == repo_full_name)
    ).scalar_one_or_none()
    if not repo:
        raise HTTPException(404, f"Repo {repo_full_name!r} not found")
    repo.is_tracked = body.is_tracked
    s.commit()
    cache_invalidate_all()
    return {"full_name": repo.full_name, "is_tracked": repo.is_tracked}


@router.get("/contributors")
def list_all_contributors(s: Session = Depends(get_session)) -> dict:
    """Every known contributor with lifetime merged PR count."""
    rows = s.execute(
        select(
            Contributor.login,
            Contributor.display_name,
            Contributor.is_tracked,
            func.count(PullRequest.id).label("prs"),
        )
        .outerjoin(PullRequest, PullRequest.author_id == Contributor.id)
        .group_by(
            Contributor.login, Contributor.display_name, Contributor.is_tracked
        )
        .order_by(func.count(PullRequest.id).desc())
    ).all()
    return {
        "contributors": [
            {
                "login": login,
                "display_name": display_name or login,
                "is_tracked": bool(tracked),
                "prs_merged_total": int(prs),
            }
            for login, display_name, tracked, prs in rows
        ]
    }


@router.patch("/contributors/{login}")
def set_contributor_tracked(
    login: str,
    body: TrackedPatch,
    s: Session = Depends(get_session),
) -> dict:
    contrib = s.execute(
        select(Contributor).where(Contributor.login == login)
    ).scalar_one_or_none()
    if not contrib:
        raise HTTPException(404, f"Contributor {login!r} not found")
    contrib.is_tracked = body.is_tracked
    s.commit()
    cache_invalidate_all()
    return {"login": contrib.login, "is_tracked": contrib.is_tracked}
