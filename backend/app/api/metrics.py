"""GET /api/v1/metrics/org — Org Overview data feed.

Returns 7 KPI values + weekly series + per-team breakdown (repo-as-team in v0).
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from .auth import require_auth
from ..metrics import deployment_frequency as df
from ..metrics import lead_time as lt
from ..metrics import pr_cycle_time as ct
from ..metrics import pr_size as sz
from ..metrics import review_coverage as rc
from ..metrics import throughput as tp
from ..metrics import time_to_first_review as ttfr
from ..models import Contributor, Deployment, PRCommit, PRReview, PullRequest, Repository

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"], dependencies=[Depends(require_auth)])

Period = Literal["30d", "90d", "6m"]

# A3: in-process TTL cache. Data only changes once per night, so a 5-minute response cache is
# very generous in freshness terms but is the bigger perf lever than snapshot reads at our
# current scale (single-instance backend, no Redis).
_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = Lock()


def _cache_get(key: str) -> dict | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, payload = entry
        if time.time() - ts > _CACHE_TTL_SECONDS:
            del _cache[key]
            return None
        return payload


def _cache_put(key: str, payload: dict) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), payload)


def cache_invalidate_all() -> None:
    """Called by the sync orchestrator after a successful sync so cached responses don't
    serve stale data for up to 5 minutes after fresh data lands."""
    with _cache_lock:
        _cache.clear()


def _period_days(p: str) -> int:
    return {"30d": 30, "90d": 90, "6m": 180}.get(p, 90)


def _date_range(period: str) -> tuple[date, date]:
    days = _period_days(period)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    return start, end


def _load_period_prs(s: Session, start: date, end: date) -> list[dict]:
    """All merged PRs in the period, with first-commit timestamp and review events attached.

    Designed to avoid the N+1 trap: one query for PRs, one for the first-commit map, one for
    all reviews. Reviews are then grouped in Python.
    """
    excluded = settings.excluded_user_set

    # First-commit per PR
    commit_map: dict[int, datetime] = {}
    for row in s.execute(select(PRCommit.pr_id, PRCommit.authored_at)).all():
        existing = commit_map.get(row.pr_id)
        if existing is None or row.authored_at < existing:
            commit_map[row.pr_id] = row.authored_at

    # PRs in window
    pr_rows = s.execute(
        select(PullRequest, Contributor.login, Repository.full_name)
        .join(Repository, PullRequest.repo_id == Repository.id)
        .outerjoin(Contributor, PullRequest.author_id == Contributor.id)
        .where(PullRequest.merged_at.is_not(None))
        .where(PullRequest.merged_at >= datetime.combine(start, datetime.min.time(), timezone.utc))
        .where(PullRequest.merged_at <= datetime.combine(end, datetime.max.time(), timezone.utc))
    ).all()
    pr_id_set = {pr.id for pr, _, _ in pr_rows}

    # Reviews for those PRs — one query, group in memory
    reviews_by_pr: dict[int, list[dict]] = defaultdict(list)
    if pr_id_set:
        rv_rows = s.execute(
            select(PRReview, Contributor.login)
            .outerjoin(Contributor, PRReview.reviewer_id == Contributor.id)
            .where(PRReview.pr_id.in_(pr_id_set))
        ).all()
        for rv, reviewer_login in rv_rows:
            reviews_by_pr[rv.pr_id].append(
                {
                    "submitted_at": rv.submitted_at,
                    "state": rv.state,
                    "reviewer_login": reviewer_login,
                }
            )

    out: list[dict] = []
    for pr, login, repo_full in pr_rows:
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
                "reviews": reviews_by_pr.get(pr.id, []),
                "ai_assisted": bool(pr.ai_assisted),
                "ai_tool": pr.ai_tool,
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
    """Return % change. None when either side is missing OR when prior is too small to be
    meaningful (avoids the "+258,400% vs prior" effect on the first backfill)."""
    if current is None or prior is None:
        return None
    # If prior is essentially zero, % change is undefined — show None rather than ±inf.
    if abs(prior) < 1e-6:
        return None
    return round(((current - prior) / prior) * 100.0, 1)


def _round_or_none(v: float | None, ndigits: int = 2) -> float | None:
    return round(v, ndigits) if v is not None else None


def _backfill_horizon(s: Session) -> date | None:
    """The honest 'we have no PR data before this date' boundary.

    Approach: take max(earliest_merged_at, today - BACKFILL_MONTHS). `opened_at` is unreliable
    because long-running PRs may have opened_at from before the sync window. `merged_at` is
    the date the PR data actually counts toward metrics.
    """
    earliest_merged = s.execute(select(func.min(PullRequest.merged_at))).scalar()
    explicit = datetime.now(timezone.utc).date() - timedelta(days=30 * settings.backfill_months)
    if earliest_merged is None:
        return explicit
    return max(earliest_merged.date(), explicit)


@router.get("/org")
def org_metrics(
    period: str = Query("90d"),
    s: Session = Depends(get_session),
) -> dict:
    cache_key = f"org:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    payload = _build_org_metrics(period, s)
    _cache_put(cache_key, payload)
    return payload


def _build_org_metrics(period: str, s: Session) -> dict:
    start, end = _date_range(period)
    prior_start = start - (end - start)
    prior_end = start

    # A1: if the prior window predates the backfill horizon, treat priors as missing rather
    # than near-zero. Avoids the "+258,400% vs prior" effect on the first sync.
    horizon = _backfill_horizon(s)
    prior_is_valid = horizon is None or prior_start >= horizon

    cur_prs = _load_period_prs(s, start, end)
    prior_prs = _load_period_prs(s, prior_start, prior_end) if prior_is_valid else []
    cur_deps = _load_period_deployments(s, start, end)
    prior_deps = _load_period_deployments(s, prior_start, prior_end) if prior_is_valid else []

    weeks_in_period = max(1, (end - start).days // 7)
    weeks_in_prior = max(1, (prior_end - prior_start).days // 7)

    # Aggregates — current
    deploy_per_week = len(cur_deps) / weeks_in_period
    throughput_per_week = len(cur_prs) / weeks_in_period
    cur_lt_p50, cur_lt_p75 = lt.aggregate(cur_prs)
    cur_ct = ct.aggregate(cur_prs)
    cur_size = sz.aggregate(cur_prs)
    cur_cov = rc.aggregate(cur_prs)
    cur_ttfr = ttfr.aggregate(cur_prs)
    cur_large_count = sz.count_large(cur_prs, settings.large_pr_threshold)

    # AI attribution — % of merged PRs flagged as AI-assisted + per-tool counts.
    def _ai_pct(prs: list[dict]) -> float | None:
        if not prs:
            return None
        return round(100.0 * sum(1 for p in prs if p["ai_assisted"]) / len(prs), 1)

    def _ai_tools_count(prs: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for p in prs:
            if p["ai_assisted"] and p["ai_tool"]:
                counts[p["ai_tool"]] += 1
        return dict(counts)

    cur_ai_pct = _ai_pct(cur_prs)
    cur_ai_tools = _ai_tools_count(cur_prs)

    # Aggregates — prior (for deltas). When the prior window predates backfill, pass None so
    # _delta_pct returns null and the UI shows "— no prior data" instead of a junk percentage.
    if prior_is_valid:
        deploy_per_week_prior: float | None = len(prior_deps) / weeks_in_prior
        throughput_per_week_prior: float | None = len(prior_prs) / weeks_in_prior
        prior_lt_p50, _ = lt.aggregate(prior_prs)
        prior_ct = ct.aggregate(prior_prs)
        prior_size = sz.aggregate(prior_prs)
        prior_cov = rc.aggregate(prior_prs)
        prior_ttfr = ttfr.aggregate(prior_prs)
        prior_ai_pct = _ai_pct(prior_prs)
    else:
        deploy_per_week_prior = None
        throughput_per_week_prior = None
        prior_lt_p50 = None
        prior_ct = {"total_p50": None, "pickup_p50": None, "review_p50": None, "merge_p50": None}
        prior_size = None
        prior_cov = None
        prior_ttfr = None
        prior_ai_pct = None

    # Weekly series
    df_series = df.per_week(cur_deps, start, end)
    lt_series = lt.per_week(cur_prs, start, end)
    tp_series = tp.per_week(cur_prs, start, end)
    ct_series = ct.per_week_phases(cur_prs, start, end)
    sz_series = sz.per_week(cur_prs, start, end)
    rc_series = rc.per_week(cur_prs, start, end)
    ttfr_series = ttfr.per_week(cur_prs, start, end)

    # AI-assisted weekly series (% of merged PRs per week with ai_assisted=True)
    ai_buckets: dict[date, list[bool]] = defaultdict(list)
    for pr in cur_prs:
        from .. import metrics as _m  # late import to avoid cycle
        from ..metrics.common import iso_week_start as _iws

        merged = pr["merged_at"]
        if merged is None:
            continue
        w = _iws(merged)
        if start <= w <= end:
            ai_buckets[w].append(pr["ai_assisted"])

    from datetime import timedelta as _td

    from ..metrics.common import iso_week_start

    ai_series: list[tuple[date, float | None]] = []
    cur = iso_week_start(start)
    last_w = iso_week_start(end)
    while cur <= last_w:
        vals = ai_buckets.get(cur, [])
        ai_series.append(
            (cur, round(100.0 * sum(vals) / len(vals), 1) if vals else None)
        )
        cur = cur + _td(days=7)

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
                "lead_time_p50_hours": _round_or_none(p50),
                "pr_cycle_time_hours": _round_or_none(ct.aggregate(prs)["total_p50"]),
                "median_pr_size_lines": _round_or_none(sz.aggregate(prs)),
                "review_coverage_pct": _round_or_none(rc.aggregate(prs)),
                "time_to_first_review_hours": _round_or_none(ttfr.aggregate(prs)),
                "ai_assisted_pct": _ai_pct(prs),
            }
        )

    return {
        "period": period,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "config": {"large_pr_threshold": settings.large_pr_threshold},
        "counts": {
            "merged_prs": len(cur_prs),
            "deployments": len(cur_deps),
            "large_prs": cur_large_count,
        },
        "kpis": {
            "deployment_frequency": {
                "value": round(deploy_per_week, 2),
                "unit": "per_week",
                "delta_pct": _delta_pct(deploy_per_week, deploy_per_week_prior),
                "bad_direction": "down",
            },
            "lead_time_p50": {
                "value": _round_or_none(cur_lt_p50),
                "unit": "hours",
                "delta_pct": _delta_pct(cur_lt_p50, prior_lt_p50),
                "bad_direction": "up",
                "p75": _round_or_none(cur_lt_p75),
            },
            "pr_throughput": {
                "value": round(throughput_per_week, 2),
                "unit": "per_week",
                "delta_pct": _delta_pct(throughput_per_week, throughput_per_week_prior),
                "bad_direction": None,
            },
            "pr_cycle_time": {
                "value": _round_or_none(cur_ct["total_p50"]),
                "unit": "hours",
                "delta_pct": _delta_pct(cur_ct["total_p50"], prior_ct["total_p50"]),
                "bad_direction": "up",
                "phases": {
                    "pickup_p50": _round_or_none(cur_ct["pickup_p50"]),
                    "review_p50": _round_or_none(cur_ct["review_p50"]),
                    "merge_p50": _round_or_none(cur_ct["merge_p50"]),
                },
            },
            "pr_size": {
                "value": _round_or_none(cur_size),
                "unit": "lines",
                "delta_pct": _delta_pct(cur_size, prior_size),
                "bad_direction": "up",
                "red_when_above": settings.large_pr_threshold,
            },
            "review_coverage": {
                "value": _round_or_none(cur_cov, 1),
                "unit": "pct",
                "delta_pct": _delta_pct(cur_cov, prior_cov),
                "bad_direction": "down",
            },
            "time_to_first_review": {
                "value": _round_or_none(cur_ttfr),
                "unit": "hours",
                "delta_pct": _delta_pct(cur_ttfr, prior_ttfr),
                "bad_direction": "up",
            },
            "ai_assisted": {
                "value": cur_ai_pct,
                "unit": "pct",
                "delta_pct": _delta_pct(cur_ai_pct, prior_ai_pct),
                # No "bad direction" — this is informational, not a value judgment.
                "bad_direction": None,
                "tools": cur_ai_tools,
            },
        },
        "series": {
            "deployment_frequency": [
                {"week": w.isoformat(), "value": v} for w, v in df_series
            ],
            "lead_time": [
                {
                    "week": w.isoformat(),
                    "p50": _round_or_none(p50),
                    "p75": _round_or_none(p75),
                }
                for w, p50, p75 in lt_series
            ],
            "pr_throughput": [{"week": w.isoformat(), "value": v} for w, v in tp_series],
            "pr_cycle_time": [
                {
                    "week": w.isoformat(),
                    "pickup": _round_or_none(pu),
                    "review": _round_or_none(rv),
                    "merge": _round_or_none(mg),
                }
                for w, pu, rv, mg in ct_series
            ],
            "pr_size": [
                {"week": w.isoformat(), "value": _round_or_none(v)} for w, v in sz_series
            ],
            "review_coverage": [
                {"week": w.isoformat(), "value": _round_or_none(v, 1)} for w, v in rc_series
            ],
            "time_to_first_review": [
                {"week": w.isoformat(), "value": _round_or_none(v)} for w, v in ttfr_series
            ],
            "ai_assisted": [{"week": w.isoformat(), "value": v} for w, v in ai_series],
        },
        "teams": teams,
    }
