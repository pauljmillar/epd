"""GET /api/v1/metrics/org — Org Overview data feed.

Returns KPI values + sparkline data + per-team breakdown (repo-as-team in v0).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..metrics import deployment_frequency as df
from ..metrics import lead_time as lt
from ..metrics import throughput as tp
from ..models import Contributor, Deployment, PRCommit, PullRequest, Repository

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

Period = Literal["30d", "90d", "6m"]


def _period_days(p: str) -> int:
    return {"30d": 30, "90d": 90, "6m": 180}.get(p, 90)


def _date_range(period: str) -> tuple[date, date]:
    days = _period_days(period)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    return start, end


def _load_period_prs(s: Session, start: date, end: date) -> list[dict]:
    """All merged PRs with their first commit, filtered by merge date and excluded users."""
    excluded = settings.excluded_user_set
    commit_map: dict[int, datetime] = {}
    for row in s.execute(select(PRCommit.pr_id, PRCommit.authored_at)).all():
        existing = commit_map.get(row.pr_id)
        if existing is None or row.authored_at < existing:
            commit_map[row.pr_id] = row.authored_at

    stmt = (
        select(PullRequest, Contributor.login, Repository.full_name)
        .join(Repository, PullRequest.repo_id == Repository.id)
        .outerjoin(Contributor, PullRequest.author_id == Contributor.id)
        .where(PullRequest.merged_at.is_not(None))
        .where(PullRequest.merged_at >= datetime.combine(start, datetime.min.time(), timezone.utc))
        .where(PullRequest.merged_at <= datetime.combine(end, datetime.max.time(), timezone.utc))
    )
    out: list[dict] = []
    for pr, login, repo_full in s.execute(stmt).all():
        if login and login in excluded:
            continue
        out.append(
            {
                "id": pr.id,
                "opened_at": pr.opened_at,
                "merged_at": pr.merged_at,
                "first_commit_at": commit_map.get(pr.id),
                "author_login": login,
                "repo_full_name": repo_full,
                "additions": pr.additions,
                "deletions": pr.deletions,
            }
        )
    return out


def _load_period_deployments(s: Session, start: date, end: date) -> list[dict]:
    stmt = (
        select(Deployment, Repository.full_name)
        .join(Repository, Deployment.repo_id == Repository.id)
        .where(Deployment.triggered_at >= datetime.combine(start, datetime.min.time(), timezone.utc))
        .where(Deployment.triggered_at <= datetime.combine(end, datetime.max.time(), timezone.utc))
    )
    return [
        {"triggered_at": d.triggered_at, "repo_full_name": full}
        for d, full in s.execute(stmt).all()
    ]


def _delta_pct(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return round(((current - prior) / prior) * 100.0, 1)


@router.get("/org")
def org_metrics(
    period: str = Query("90d"),
    s: Session = Depends(get_session),
) -> dict:
    start, end = _date_range(period)
    prior_start = start - (end - start)
    prior_end = start

    cur_prs = _load_period_prs(s, start, end)
    prior_prs = _load_period_prs(s, prior_start, prior_end)
    cur_deps = _load_period_deployments(s, start, end)
    prior_deps = _load_period_deployments(s, prior_start, prior_end)

    # KPIs
    weeks_in_period = max(1, (end - start).days // 7)
    deploy_per_week = len(cur_deps) / weeks_in_period
    deploy_per_week_prior = len(prior_deps) / max(1, (prior_end - prior_start).days // 7)

    cur_lt_p50, cur_lt_p75 = lt.aggregate(cur_prs)
    prior_lt_p50, _ = lt.aggregate(prior_prs)

    throughput_per_week = len(cur_prs) / weeks_in_period
    throughput_per_week_prior = len(prior_prs) / max(1, (prior_end - prior_start).days // 7)

    # Sparkline series (weekly)
    df_series = df.per_week(cur_deps, start, end)
    lt_series = lt.per_week(cur_prs, start, end)
    tp_series = tp.per_week(cur_prs, start, end)

    # Per-repo (pseudo-team) breakdown
    by_repo: dict[str, list[dict]] = {}
    for pr in cur_prs:
        by_repo.setdefault(pr["repo_full_name"], []).append(pr)
    deps_by_repo: dict[str, list[dict]] = {}
    for d in cur_deps:
        deps_by_repo.setdefault(d["repo_full_name"], []).append(d)

    teams = []
    for repo, prs in sorted(by_repo.items()):
        p50, _ = lt.aggregate(prs)
        teams.append(
            {
                "name": repo,
                "prs_merged": len(prs),
                "throughput_per_week": round(len(prs) / weeks_in_period, 2),
                "deploy_per_week": round(
                    len(deps_by_repo.get(repo, [])) / weeks_in_period, 2
                ),
                "lead_time_p50_hours": round(p50, 2) if p50 is not None else None,
            }
        )

    return {
        "period": period,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "kpis": {
            "deployment_frequency": {
                "value": round(deploy_per_week, 2),
                "unit": "per_week",
                "delta_pct": _delta_pct(deploy_per_week, deploy_per_week_prior),
                "bad_direction": "down",
            },
            "lead_time_p50": {
                "value": round(cur_lt_p50, 2) if cur_lt_p50 is not None else None,
                "unit": "hours",
                "delta_pct": _delta_pct(cur_lt_p50, prior_lt_p50),
                "bad_direction": "up",
                "p75": round(cur_lt_p75, 2) if cur_lt_p75 is not None else None,
            },
            "pr_throughput": {
                "value": round(throughput_per_week, 2),
                "unit": "per_week",
                "delta_pct": _delta_pct(throughput_per_week, throughput_per_week_prior),
                "bad_direction": None,
            },
        },
        "series": {
            "deployment_frequency": [
                {"week": w.isoformat(), "value": v} for w, v in df_series
            ],
            "lead_time": [
                {
                    "week": w.isoformat(),
                    "p50": round(p50, 2) if p50 is not None else None,
                    "p75": round(p75, 2) if p75 is not None else None,
                }
                for w, p50, p75 in lt_series
            ],
            "pr_throughput": [{"week": w.isoformat(), "value": v} for w, v in tp_series],
        },
        "teams": teams,
    }
