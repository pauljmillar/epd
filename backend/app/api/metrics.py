"""GET /api/v1/metrics/{org|team|contributor} — dashboard data feeds.

The heart of this module is `_compute_metrics(prs, deps, ...)`, a pure function that takes
already-loaded PRs and deployments and produces the KPI + series payload. The three
endpoints (`/org`, `/team/{name}`, `/contributor/{login}`) all delegate to it after loading
their scoped slice of PRs.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..metrics import deployment_frequency as df
from ..metrics import lead_time as lt
from ..metrics import pr_cycle_time as ct
from ..metrics import pr_size as sz
from ..metrics import review_coverage as rc
from ..metrics import throughput as tp
from ..metrics import time_to_first_review as ttfr
from ..metrics.common import iso_week_start
from ..models import Contributor, Deployment, PRCommit, PRReview, PullRequest, Repository
from .auth import require_auth

router = APIRouter(
    prefix="/api/v1/metrics", tags=["metrics"], dependencies=[Depends(require_auth)]
)

# --- TTL cache ---------------------------------------------------------------

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
    """Called by the sync orchestrator after a successful sync."""
    with _cache_lock:
        _cache.clear()


# --- Period helpers ----------------------------------------------------------


def _period_days(p: str) -> int:
    return {"30d": 30, "90d": 90, "6m": 180}.get(p, 90)


def _date_range(period: str) -> tuple[date, date]:
    days = _period_days(period)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    return start, end


def _backfill_horizon(s: Session) -> date | None:
    earliest_merged = s.execute(select(func.min(PullRequest.merged_at))).scalar()
    explicit = datetime.now(timezone.utc).date() - timedelta(days=30 * settings.backfill_months)
    if earliest_merged is None:
        return explicit
    return max(earliest_merged.date(), explicit)


def _delta_pct(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None:
        return None
    if abs(prior) < 1e-6:
        return None
    return round(((current - prior) / prior) * 100.0, 1)


def _round_or_none(v: float | None, ndigits: int = 2) -> float | None:
    return round(v, ndigits) if v is not None else None


def resolve_team_member_logins(s: Session, team_id: int) -> list[str]:
    """Return all contributor logins for the given team. Empty list if team is missing or
    has no members — _load_period_prs's author_logins short-circuits on empty so this
    yields the natural 'no PRs' result rather than a 500."""
    from ..models import TeamMember

    return [
        row[0]
        for row in s.execute(
            select(Contributor.login)
            .join(TeamMember, TeamMember.contributor_id == Contributor.id)
            .where(TeamMember.team_id == team_id)
        ).all()
    ]


# --- Loaders -----------------------------------------------------------------


def _load_period_prs(
    s: Session,
    start: date,
    end: date,
    *,
    repo_full_name: str | None = None,
    author_login: str | None = None,
    author_logins: list[str] | None = None,
) -> list[dict]:
    """Load merged PRs in [start, end] with first-commit + reviews attached. Optional filters
    compose: one repo and/or one author and/or a set of author logins (for team scoping)."""
    excluded = settings.excluded_user_set

    # First-commit per PR
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
        # CP+: skip PRs from untracked repos or untracked authors. Author may be NULL (bot
        # PRs with no contributor row); those pass through.
        .where(Repository.is_tracked.is_(True))
        .where((Contributor.is_tracked.is_(True)) | (Contributor.id.is_(None)))
    )
    if repo_full_name is not None:
        stmt = stmt.where(Repository.full_name == repo_full_name)
    if author_login is not None:
        stmt = stmt.where(Contributor.login == author_login)
    if author_logins is not None:
        if not author_logins:
            # An explicit empty member list means "no PRs".
            return []
        stmt = stmt.where(Contributor.login.in_(author_logins))

    pr_rows = s.execute(stmt).all()
    pr_id_set = {pr.id for pr, _, _ in pr_rows}

    reviews_by_pr: dict[int, list[dict]] = defaultdict(list)
    if pr_id_set:
        for rv, reviewer_login in s.execute(
            select(PRReview, Contributor.login)
            .outerjoin(Contributor, PRReview.reviewer_id == Contributor.id)
            .where(PRReview.pr_id.in_(pr_id_set))
        ).all():
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
                "number": pr.number,
                "title": pr.title,
                "url": pr.url,
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


def _load_period_deployments(
    s: Session,
    start: date,
    end: date,
    *,
    repo_full_name: str | None = None,
    in_repo_full_names: list[str] | None = None,
) -> list[dict]:
    """Deployments triggered in [start, end] from tracked repos. Filters compose:
    - `repo_full_name`: single-repo scope (Repo Detail).
    - `in_repo_full_names`: restrict to a set (e.g. "repos this team has worked in").
    """
    stmt = (
        select(Deployment, Repository.full_name)
        .join(Repository, Deployment.repo_id == Repository.id)
        .where(Deployment.triggered_at >= datetime.combine(start, datetime.min.time(), timezone.utc))
        .where(Deployment.triggered_at <= datetime.combine(end, datetime.max.time(), timezone.utc))
        .where(Repository.is_tracked.is_(True))
    )
    if repo_full_name is not None:
        stmt = stmt.where(Repository.full_name == repo_full_name)
    if in_repo_full_names is not None:
        if not in_repo_full_names:
            # Team had zero repo activity → no deployments to attribute.
            return []
        stmt = stmt.where(Repository.full_name.in_(in_repo_full_names))
    return [
        {"triggered_at": d.triggered_at, "repo_full_name": full}
        for d, full in s.execute(stmt).all()
    ]


# --- Aggregation -------------------------------------------------------------


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


def _ai_series_per_week(prs: list[dict], start: date, end: date) -> list[tuple[date, float | None]]:
    buckets: dict[date, list[bool]] = defaultdict(list)
    for pr in prs:
        merged = pr["merged_at"]
        if merged is None:
            continue
        w = iso_week_start(merged)
        if start <= w <= end:
            buckets[w].append(pr["ai_assisted"])
    out: list[tuple[date, float | None]] = []
    cur = iso_week_start(start)
    last_w = iso_week_start(end)
    while cur <= last_w:
        vals = buckets.get(cur, [])
        out.append((cur, round(100.0 * sum(vals) / len(vals), 1) if vals else None))
        cur = cur + timedelta(days=7)
    return out


def _compute_kpis(
    cur_prs: list[dict],
    cur_deps: list[dict],
    prior_prs: list[dict] | None,
    prior_deps: list[dict] | None,
    start: date,
    end: date,
    prior_start: date,
    prior_end: date,
) -> dict:
    """Return the kpis + series + counts payload for an arbitrary set of PRs/deps."""
    weeks_in_period = max(1, (end - start).days // 7)
    weeks_in_prior = max(1, (prior_end - prior_start).days // 7)

    # Current
    deploy_per_week = len(cur_deps) / weeks_in_period
    throughput_per_week = len(cur_prs) / weeks_in_period
    cur_lt_p50, cur_lt_p75 = lt.aggregate(cur_prs)
    cur_ct = ct.aggregate(cur_prs)
    cur_size = sz.aggregate(cur_prs)
    cur_cov = rc.aggregate(cur_prs)
    cur_ttfr = ttfr.aggregate(cur_prs)
    cur_large_count = sz.count_large(cur_prs, settings.large_pr_threshold)
    cur_ai_pct = _ai_pct(cur_prs)
    cur_ai_tools = _ai_tools_count(cur_prs)

    # Prior — None when prior window is invalid
    if prior_prs is not None and prior_deps is not None:
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

    # Series
    df_series = df.per_week(cur_deps, start, end)
    lt_series = lt.per_week(cur_prs, start, end)
    tp_series = tp.per_week(cur_prs, start, end)
    ct_series = ct.per_week_phases(cur_prs, start, end)
    sz_series = sz.per_week(cur_prs, start, end)
    rc_series = rc.per_week(cur_prs, start, end)
    ttfr_series = ttfr.per_week(cur_prs, start, end)
    ai_series = _ai_series_per_week(cur_prs, start, end)

    return {
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
                "bad_direction": None,
                "tools": cur_ai_tools,
            },
        },
        "series": {
            "deployment_frequency": [{"week": w.isoformat(), "value": v} for w, v in df_series],
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
    }


def _notable_prs_by_lead_time(prs: list[dict], n: int = 5) -> list[dict]:
    """Top N PRs by longest lead time (first_commit → merge)."""
    with_lt: list[tuple[float, dict]] = []
    for pr in prs:
        lt_hours = lt.lead_time_hours(pr)
        if lt_hours is not None:
            with_lt.append((lt_hours, pr))
    with_lt.sort(key=lambda t: -t[0])
    out = []
    for lt_hours, pr in with_lt[:n]:
        out.append(
            {
                "number": pr["number"],
                "title": pr["title"],
                "url": pr["url"],
                "repo": pr["repo_full_name"],
                "author": pr["author_login"],
                "lead_time_hours": round(lt_hours, 2),
            }
        )
    return out


# --- Endpoints ---------------------------------------------------------------


@router.get("/org")
def org_metrics(
    period: str = Query("30d"),
    team: int | None = Query(None),
    s: Session = Depends(get_session),
) -> dict:
    cache_key = f"org:{period}:team:{team or 'all'}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # When team is set, scope every PR query to its members. Unknown team => empty list
    # which short-circuits _load_period_prs to "no PRs" — the natural "no data" shape.
    member_logins = resolve_team_member_logins(s, team) if team is not None else None

    start, end = _date_range(period)
    prior_start = start - (end - start)
    prior_end = start
    horizon = _backfill_horizon(s)
    prior_is_valid = horizon is None or prior_start >= horizon

    cur_prs = _load_period_prs(s, start, end, author_logins=member_logins)
    # When team filter is active, scope deployments to repos the team has any PR activity
    # in. Without this, the deploy-freq KPI would stay org-wide and confusingly not change
    # when the team filter is toggled.
    team_repo_filter = (
        sorted({pr["repo_full_name"] for pr in cur_prs}) if team is not None else None
    )
    cur_deps = _load_period_deployments(s, start, end, in_repo_full_names=team_repo_filter)
    if prior_is_valid:
        prior_prs = _load_period_prs(s, prior_start, prior_end, author_logins=member_logins)
        prior_team_repo_filter = (
            sorted({pr["repo_full_name"] for pr in prior_prs}) if team is not None else None
        )
        prior_deps = _load_period_deployments(
            s, prior_start, prior_end, in_repo_full_names=prior_team_repo_filter
        )
    else:
        prior_prs = None
        prior_deps = None

    payload = _compute_kpis(cur_prs, cur_deps, prior_prs, prior_deps, start, end, prior_start, prior_end)
    payload["period"] = period
    payload["team_id"] = team
    payload["range"] = {"start": start.isoformat(), "end": end.isoformat()}
    payload["config"] = {"large_pr_threshold": settings.large_pr_threshold}
    payload["notable_prs"] = {"lead_time": _notable_prs_by_lead_time(cur_prs)}

    # Per-repo (pseudo-team) breakdown
    weeks_in_period = max(1, (end - start).days // 7)
    by_repo: dict[str, list[dict]] = {}
    for pr in cur_prs:
        by_repo.setdefault(pr["repo_full_name"], []).append(pr)
    deps_by_repo: dict[str, list[dict]] = {}
    for d in cur_deps:
        deps_by_repo.setdefault(d["repo_full_name"], []).append(d)

    repos = []
    for repo, prs in sorted(by_repo.items()):
        p50, _ = lt.aggregate(prs)
        repos.append(
            {
                "full_name": repo,
                "prs_merged": len(prs),
                "throughput_per_week": round(len(prs) / weeks_in_period, 2),
                "deploy_per_week": round(len(deps_by_repo.get(repo, [])) / weeks_in_period, 2),
                "lead_time_p50_hours": _round_or_none(p50),
                "pr_cycle_time_hours": _round_or_none(ct.aggregate(prs)["total_p50"]),
                "median_pr_size_lines": _round_or_none(sz.aggregate(prs)),
                "review_coverage_pct": _round_or_none(rc.aggregate(prs)),
                "time_to_first_review_hours": _round_or_none(ttfr.aggregate(prs)),
                "ai_assisted_pct": _ai_pct(prs),
            }
        )
    payload["repos"] = repos

    _cache_put(cache_key, payload)
    return payload


@router.get("/repo/{repo_full_name:path}")
def repo_metrics(
    repo_full_name: str,
    period: str = Query("30d"),
    team: int | None = Query(None),
    s: Session = Depends(get_session),
) -> dict:
    cache_key = f"repo:{repo_full_name}:{period}:team:{team or 'all'}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    exists = s.execute(
        select(Repository.id).where(Repository.full_name == repo_full_name)
    ).first()
    if not exists:
        raise HTTPException(404, f"Repo {repo_full_name!r} not found")

    member_logins = resolve_team_member_logins(s, team) if team is not None else None

    start, end = _date_range(period)
    prior_start = start - (end - start)
    prior_end = start
    horizon = _backfill_horizon(s)
    prior_is_valid = horizon is None or prior_start >= horizon

    cur_prs = _load_period_prs(
        s, start, end, repo_full_name=repo_full_name, author_logins=member_logins
    )
    cur_deps = _load_period_deployments(s, start, end, repo_full_name=repo_full_name)
    if prior_is_valid:
        prior_prs = _load_period_prs(
            s, prior_start, prior_end,
            repo_full_name=repo_full_name, author_logins=member_logins,
        )
        prior_deps = _load_period_deployments(s, prior_start, prior_end, repo_full_name=repo_full_name)
    else:
        prior_prs = None
        prior_deps = None

    payload = _compute_kpis(cur_prs, cur_deps, prior_prs, prior_deps, start, end, prior_start, prior_end)
    payload["period"] = period
    payload["team_id"] = team
    payload["range"] = {"start": start.isoformat(), "end": end.isoformat()}
    payload["config"] = {"large_pr_threshold": settings.large_pr_threshold}
    payload["repo"] = {"full_name": repo_full_name}
    payload["notable_prs"] = {"lead_time": _notable_prs_by_lead_time(cur_prs)}

    # Contributor context table — per-author stats inside this team
    weeks_in_period = max(1, (end - start).days // 7)
    by_author: dict[str, list[dict]] = {}
    for pr in cur_prs:
        login = pr["author_login"]
        if login:
            by_author.setdefault(login, []).append(pr)
    contributors = []
    for login, prs in sorted(by_author.items(), key=lambda t: -len(t[1])):
        p50, _ = lt.aggregate(prs)
        contributors.append(
            {
                "login": login,
                "prs_merged": len(prs),
                "throughput_per_week": round(len(prs) / weeks_in_period, 2),
                "lead_time_p50_hours": _round_or_none(p50),
                "pr_cycle_time_hours": _round_or_none(ct.aggregate(prs)["total_p50"]),
                "median_pr_size_lines": _round_or_none(sz.aggregate(prs)),
                "review_coverage_pct": _round_or_none(rc.aggregate(prs)),
                "time_to_first_review_hours": _round_or_none(ttfr.aggregate(prs)),
                "ai_assisted_pct": _ai_pct(prs),
            }
        )
    payload["contributors"] = contributors

    _cache_put(cache_key, payload)
    return payload


@router.get("/contributor/{login}")
def contributor_metrics(
    login: str,
    period: str = Query("30d"),
    s: Session = Depends(get_session),
) -> dict:
    cache_key = f"contributor:{login}:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    exists = s.execute(select(Contributor.id).where(Contributor.login == login)).first()
    if not exists:
        raise HTTPException(404, f"Contributor {login!r} not found")

    start, end = _date_range(period)
    prior_start = start - (end - start)
    prior_end = start
    horizon = _backfill_horizon(s)
    prior_is_valid = horizon is None or prior_start >= horizon

    cur_prs = _load_period_prs(s, start, end, author_login=login)
    if prior_is_valid:
        prior_prs = _load_period_prs(s, prior_start, prior_end, author_login=login)
    else:
        prior_prs = None
    # Contributors don't "own" deployments; use empty lists so the deploy KPI is 0/null.
    cur_deps: list[dict] = []
    prior_deps_arg = [] if prior_is_valid else None

    payload = _compute_kpis(cur_prs, cur_deps, prior_prs, prior_deps_arg, start, end, prior_start, prior_end)
    payload["period"] = period
    payload["range"] = {"start": start.isoformat(), "end": end.isoformat()}
    payload["config"] = {"large_pr_threshold": settings.large_pr_threshold}
    payload["contributor"] = {"login": login}

    # "Vs team median" context: for each repo this contributor touched, compute the team
    # aggregates and average them weighted by PR count. Honest comparison since teams=repos.
    repos_touched = {pr["repo_full_name"] for pr in cur_prs}
    team_prs: list[dict] = []
    for repo in repos_touched:
        team_prs.extend(_load_period_prs(s, start, end, repo_full_name=repo))
    team_lt_p50, _ = lt.aggregate(team_prs)
    payload["team_median"] = {
        "lead_time_p50_hours": _round_or_none(team_lt_p50),
        "pr_cycle_time_hours": _round_or_none(ct.aggregate(team_prs)["total_p50"]),
        "median_pr_size_lines": _round_or_none(sz.aggregate(team_prs)),
        "review_coverage_pct": _round_or_none(rc.aggregate(team_prs)),
        "time_to_first_review_hours": _round_or_none(ttfr.aggregate(team_prs)),
        "prs_merged": len(team_prs),
    }

    # Recent PRs — last 20 merged
    recent = sorted(cur_prs, key=lambda p: p["merged_at"], reverse=True)[:20]
    payload["recent_prs"] = [
        {
            "number": pr["number"],
            "title": pr["title"],
            "url": pr["url"],
            "repo": pr["repo_full_name"],
            "merged_at": pr["merged_at"].isoformat() if pr["merged_at"] else None,
            "additions": pr["additions"],
            "deletions": pr["deletions"],
            "lead_time_hours": _round_or_none(lt.lead_time_hours(pr)),
            "ai_assisted": pr["ai_assisted"],
            "ai_tool": pr["ai_tool"],
        }
        for pr in recent
    ]

    _cache_put(cache_key, payload)
    return payload


@router.get("/repos")
def list_repos(s: Session = Depends(get_session)) -> dict:
    """List tracked repos with PR count over the last 90d for sidebar ordering."""
    cache_key = "repos_list"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    start, _end = _date_range("90d")
    rows = s.execute(
        select(
            Repository.full_name,
            func.count(PullRequest.id).label("prs"),
        )
        .outerjoin(
            PullRequest,
            (PullRequest.repo_id == Repository.id)
            & (PullRequest.merged_at.is_not(None))
            & (PullRequest.merged_at >= datetime.combine(start, datetime.min.time(), timezone.utc)),
        )
        .where(Repository.is_tracked.is_(True))
        .group_by(Repository.full_name)
        .order_by(func.count(PullRequest.id).desc())
    ).all()
    payload = {"repos": [{"full_name": full, "prs_merged_90d": int(prs)} for full, prs in rows]}
    _cache_put(cache_key, payload)
    return payload


@router.get("/contributors")
def list_contributors(
    repo: str | None = Query(None),
    limit: int = Query(200, le=500),
    s: Session = Depends(get_session),
) -> dict:
    """List contributors ordered by 90-day PR count. Optional repo= filter."""
    cache_key = f"contributors_list:{repo}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    start, _end = _date_range("90d")
    stmt = (
        select(Contributor.login, Contributor.display_name, func.count(PullRequest.id).label("prs"))
        .join(PullRequest, PullRequest.author_id == Contributor.id)
        .where(PullRequest.merged_at.is_not(None))
        .where(PullRequest.merged_at >= datetime.combine(start, datetime.min.time(), timezone.utc))
        .where(Contributor.is_tracked.is_(True))
        .group_by(Contributor.login, Contributor.display_name)
        .order_by(func.count(PullRequest.id).desc())
        .limit(limit)
    )
    if repo is not None:
        stmt = stmt.join(Repository, PullRequest.repo_id == Repository.id).where(
            Repository.full_name == repo
        )
    rows = s.execute(stmt).all()
    payload = {
        "contributors": [
            {
                "login": login,
                "display_name": display_name or login,
                "prs_merged_90d": int(prs),
            }
            for login, display_name, prs in rows
        ]
    }
    _cache_put(cache_key, payload)
    return payload
