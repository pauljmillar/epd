"""Real teams — groups of contributors that can span multiple repos.

Distinct from the per-repo "team" pseudo-concept used in v0 (which is now correctly called
a repo). A team here is a named group with explicit member contributors.

Schema is already in place (`teams` + `team_members` from migration 0001) — this is the
first time those tables are actually written/read.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import Contributor, PullRequest, Team, TeamMember
from .auth import require_auth
from .metrics import (
    _backfill_horizon,
    _compute_kpis,
    _date_range,
    _load_period_prs,
    _notable_prs_by_lead_time,
    _round_or_none,
    cache_invalidate_all,
    resolve_team_member_logins,
)

router = APIRouter(prefix="/api/v1/teams", tags=["teams"], dependencies=[Depends(require_auth)])


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class MemberAdd(BaseModel):
    login: str = Field(min_length=1, max_length=128)


@router.get("")
def list_teams(s: Session = Depends(get_session)) -> dict:
    rows = s.execute(
        select(
            Team.id,
            Team.name,
            func.count(TeamMember.contributor_id).label("members"),
        )
        .outerjoin(TeamMember, TeamMember.team_id == Team.id)
        .group_by(Team.id, Team.name)
        .order_by(Team.name)
    ).all()
    return {"teams": [{"id": tid, "name": n, "members": int(m)} for tid, n, m in rows]}


@router.post("")
def create_team(body: TeamCreate, s: Session = Depends(get_session)) -> dict:
    existing = s.execute(select(Team).where(Team.name == body.name)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"Team {body.name!r} already exists")
    team = Team(name=body.name)
    s.add(team)
    s.flush()
    s.commit()
    cache_invalidate_all()
    return {"id": team.id, "name": team.name, "members": 0}


@router.delete("/{team_id}")
def delete_team(team_id: int, s: Session = Depends(get_session)) -> dict:
    team = s.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    s.execute(
        TeamMember.__table__.delete().where(TeamMember.team_id == team_id)
    )
    s.delete(team)
    s.commit()
    cache_invalidate_all()
    return {"ok": True}


@router.get("/{team_id}/members")
def list_members(team_id: int, s: Session = Depends(get_session)) -> dict:
    team = s.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    rows = s.execute(
        select(Contributor.login, Contributor.display_name)
        .join(TeamMember, TeamMember.contributor_id == Contributor.id)
        .where(TeamMember.team_id == team_id)
        .order_by(Contributor.login)
    ).all()
    return {
        "team": {"id": team.id, "name": team.name},
        "members": [
            {"login": login, "display_name": display_name or login}
            for login, display_name in rows
        ],
    }


@router.post("/{team_id}/members")
def add_member(team_id: int, body: MemberAdd, s: Session = Depends(get_session)) -> dict:
    team = s.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    contrib = s.execute(
        select(Contributor).where(Contributor.login == body.login)
    ).scalar_one_or_none()
    if not contrib:
        raise HTTPException(404, f"Contributor {body.login!r} not found")
    existing = s.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.contributor_id == contrib.id
        )
    ).scalar_one_or_none()
    if existing:
        return {"ok": True, "already_member": True}
    s.add(TeamMember(team_id=team_id, contributor_id=contrib.id))
    s.commit()
    cache_invalidate_all()
    return {"ok": True}


@router.delete("/{team_id}/members/{login}")
def remove_member(team_id: int, login: str, s: Session = Depends(get_session)) -> dict:
    contrib = s.execute(
        select(Contributor).where(Contributor.login == login)
    ).scalar_one_or_none()
    if not contrib:
        raise HTTPException(404, "Contributor not found")
    s.execute(
        TeamMember.__table__.delete().where(
            (TeamMember.team_id == team_id) & (TeamMember.contributor_id == contrib.id)
        )
    )
    s.commit()
    cache_invalidate_all()
    return {"ok": True}


@router.get("/{team_id}/metrics")
def team_metrics(
    team_id: int,
    period: str = "30d",
    s: Session = Depends(get_session),
) -> dict:
    """Metrics scoped to PRs authored by members of this team across all repos."""
    team = s.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")

    member_logins = resolve_team_member_logins(s, team_id)

    start, end = _date_range(period)
    prior_start = start - (end - start)
    prior_end = start
    horizon = _backfill_horizon(s)
    prior_is_valid = horizon is None or prior_start >= horizon

    cur_prs = _load_period_prs(s, start, end, author_logins=member_logins)
    if prior_is_valid:
        prior_prs = _load_period_prs(s, prior_start, prior_end, author_logins=member_logins)
    else:
        prior_prs = None
    # Teams don't own deployments — they aggregate person-level PR work.
    cur_deps: list[dict] = []
    prior_deps_arg = [] if prior_is_valid else None

    payload = _compute_kpis(
        cur_prs, cur_deps, prior_prs, prior_deps_arg, start, end, prior_start, prior_end
    )
    payload["period"] = period
    payload["range"] = {"start": start.isoformat(), "end": end.isoformat()}
    payload["config"] = {"large_pr_threshold": settings.large_pr_threshold}
    payload["team"] = {
        "id": team.id,
        "name": team.name,
        "members": [
            {"login": m, "display_name": m} for m in sorted(member_logins)
        ],
    }
    payload["notable_prs"] = {"lead_time": _notable_prs_by_lead_time(cur_prs)}

    # Per-repo breakdown (across this team's footprint)
    weeks_in_period = max(1, (end - start).days // 7)
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for pr in cur_prs:
        by_repo[pr["repo_full_name"]].append(pr)
    from ..metrics import lead_time as lt

    payload["repos"] = sorted(
        [
            {
                "full_name": repo,
                "prs_merged": len(prs),
                "throughput_per_week": round(len(prs) / weeks_in_period, 2),
                "lead_time_p50_hours": _round_or_none(lt.aggregate(prs)[0]),
            }
            for repo, prs in by_repo.items()
        ],
        key=lambda r: -r["prs_merged"],
    )

    # Per-member breakdown
    by_member: dict[str, list[dict]] = defaultdict(list)
    for pr in cur_prs:
        if pr["author_login"]:
            by_member[pr["author_login"]].append(pr)
    payload["members_breakdown"] = sorted(
        [
            {
                "login": login,
                "prs_merged": len(prs),
                "throughput_per_week": round(len(prs) / weeks_in_period, 2),
                "lead_time_p50_hours": _round_or_none(lt.aggregate(prs)[0]),
            }
            for login, prs in by_member.items()
        ],
        key=lambda m: -m["prs_merged"],
    )

    return payload
