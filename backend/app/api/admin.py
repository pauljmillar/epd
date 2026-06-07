"""Admin endpoints — is_tracked toggles for repos/contributors and CRUD for data_sources.

Distinct from /metrics/repos and /metrics/contributors (which only return tracked rows for
the dashboard sidebar). Admin views return everything so the user can flip toggles.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import (
    Contributor,
    DataSource,
    Deployment,
    PRCommit,
    PRReview,
    PullRequest,
    Repository,
)
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


# --- data_sources CRUD ------------------------------------------------------


def _serialize_source(s: Session, ds: DataSource) -> dict:
    """Detail row for the UI: counts of attached repos + PRs."""
    repo_q = select(func.count(Repository.id)).where(Repository.data_source_id == ds.id)
    repo_count = int(s.execute(repo_q).scalar() or 0)

    pr_q = (
        select(func.count(PullRequest.id))
        .join(Repository, PullRequest.repo_id == Repository.id)
        .where(Repository.data_source_id == ds.id)
    )
    pr_count = int(s.execute(pr_q).scalar() or 0)

    return {
        "id": ds.id,
        "source": ds.source,
        "org_or_group": ds.org_or_group,
        "is_active": ds.is_active,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "last_synced_at": ds.last_synced_at.isoformat() if ds.last_synced_at else None,
        "repo_count": repo_count,
        "pr_count": pr_count,
        # Token deliberately NOT returned — admin re-enters to rotate.
        "token_preview": (ds.token[:4] + "…" + ds.token[-4:]) if ds.token else "",
    }


class SourceCreate(BaseModel):
    source: str = Field(pattern="^(github|gitlab)$")
    org_or_group: str = Field(min_length=1, max_length=256)
    token: str = Field(min_length=1)


class SourcePatch(BaseModel):
    token: str | None = None
    is_active: bool | None = None


@router.get("/sources")
def list_sources(s: Session = Depends(get_session)) -> dict:
    rows = s.execute(select(DataSource).order_by(DataSource.created_at)).scalars().all()
    return {"sources": [_serialize_source(s, ds) for ds in rows]}


@router.post("/sources", status_code=201)
def create_source(body: SourceCreate, s: Session = Depends(get_session)) -> dict:
    existing = s.execute(
        select(DataSource).where(
            DataSource.source == body.source,
            DataSource.org_or_group == body.org_or_group,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"Source {body.source}/{body.org_or_group} already exists")
    ds = DataSource(
        source=body.source,
        org_or_group=body.org_or_group,
        token=body.token,
        is_active=True,
    )
    s.add(ds)
    s.commit()
    s.refresh(ds)
    cache_invalidate_all()
    return _serialize_source(s, ds)


@router.patch("/sources/{source_id}")
def update_source(
    source_id: int, body: SourcePatch, s: Session = Depends(get_session)
) -> dict:
    ds = s.get(DataSource, source_id)
    if not ds:
        raise HTTPException(404, "Source not found")
    if body.token is not None:
        ds.token = body.token
    if body.is_active is not None:
        ds.is_active = body.is_active
        # When re-activating, restore tracking on all of this source's repos so they
        # come back to the dashboard immediately.
        if body.is_active:
            s.execute(
                Repository.__table__.update()
                .where(Repository.data_source_id == source_id)
                .values(is_tracked=True)
            )
    s.commit()
    s.refresh(ds)
    cache_invalidate_all()
    return _serialize_source(s, ds)


@router.delete("/sources/{source_id}")
def soft_remove_source(source_id: int, s: Session = Depends(get_session)) -> dict:
    """Soft remove: deactivate the source AND set is_tracked=false on its repos.
    Data stays in the DB. Use POST /sources/{id}/purge for a hard delete."""
    ds = s.get(DataSource, source_id)
    if not ds:
        raise HTTPException(404, "Source not found")
    ds.is_active = False
    s.execute(
        Repository.__table__.update()
        .where(Repository.data_source_id == source_id)
        .values(is_tracked=False)
    )
    s.commit()
    cache_invalidate_all()
    return {"ok": True, "id": source_id, "soft_removed": True}


@router.post("/sources/{source_id}/purge")
def purge_source(source_id: int, s: Session = Depends(get_session)) -> dict:
    """Hard delete: remove every PR, review, commit, deployment, snapshot, and the source
    itself. Contributors are left alone (a contributor may legitimately exist for multiple
    sources or be referenced by team_members)."""
    ds = s.get(DataSource, source_id)
    if not ds:
        raise HTTPException(404, "Source not found")

    repo_ids = [
        rid
        for (rid,) in s.execute(
            select(Repository.id).where(Repository.data_source_id == source_id)
        ).all()
    ]

    if repo_ids:
        pr_ids = [
            pid
            for (pid,) in s.execute(
                select(PullRequest.id).where(PullRequest.repo_id.in_(repo_ids))
            ).all()
        ]
        if pr_ids:
            s.execute(delete(PRReview).where(PRReview.pr_id.in_(pr_ids)))
            s.execute(delete(PRCommit).where(PRCommit.pr_id.in_(pr_ids)))
            s.execute(delete(PullRequest).where(PullRequest.id.in_(pr_ids)))
        s.execute(delete(Deployment).where(Deployment.repo_id.in_(repo_ids)))
        # contributor_month_snapshots reference repo_id but not the source directly
        from ..models import ContributorMonthSnapshot

        s.execute(
            delete(ContributorMonthSnapshot).where(
                ContributorMonthSnapshot.repo_id.in_(repo_ids)
            )
        )
        s.execute(delete(Repository).where(Repository.id.in_(repo_ids)))

    s.delete(ds)
    s.commit()
    cache_invalidate_all()
    return {
        "ok": True,
        "id": source_id,
        "purged": True,
        "deleted_repos": len(repo_ids),
    }


@router.post("/sources/{source_id}/sync")
async def trigger_source_sync(source_id: int, s: Session = Depends(get_session)) -> dict:
    ds = s.get(DataSource, source_id)
    if not ds:
        raise HTTPException(404, "Source not found")
    if not ds.is_active:
        raise HTTPException(400, "Source is not active")
    # Reuse the existing in-process sync. This blocks the request thread until done; the
    # frontend should treat the call as fire-and-forget and poll /sync/status afterward.
    from ..sync import run_sync

    result = await run_sync(only_data_source_id=source_id)
    return result
