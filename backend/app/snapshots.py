"""Build contributor_month_snapshots from raw PRs/commits/deployments/reviews.

BRD §8: monthly snapshots are immutable once finalized. The current (incomplete) month is
recalculated nightly; prior months are recalculated only until finalization runs on the 1st.

Populates every column in the snapshot schema so the read path can switch from live
recompute to snapshot reads in a follow-up (BACKLOG A2 read-path item).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import session_scope
from .metrics import lead_time as lt
from .metrics import pr_cycle_time as ct
from .metrics import pr_size as sz
from .metrics import review_coverage as rc
from .metrics import time_to_first_review as ttfr
from .metrics.common import year_month
from .models import (
    Contributor,
    ContributorMonthSnapshot,
    Deployment,
    PRCommit,
    PRReview,
    PullRequest,
    SyncLog,
)

log = logging.getLogger(__name__)


def _current_year_month() -> str:
    return year_month(datetime.now(timezone.utc))


def rebuild_current_period() -> int:
    return rebuild_month(_current_year_month())


def rebuild_month(ym: str) -> int:
    """Rebuild snapshots for a given YYYY-MM. Skips rows already marked is_finalized."""
    written = 0
    with session_scope() as s:
        # First-commit lookup per PR
        commit_map: dict[int, datetime] = {}
        for row in s.execute(select(PRCommit.pr_id, PRCommit.authored_at)).all():
            existing = commit_map.get(row.pr_id)
            if existing is None or row.authored_at < existing:
                commit_map[row.pr_id] = row.authored_at

        # Reviews per PR, with reviewer login (for coverage / first-review math)
        reviews_by_pr: dict[int, list[dict]] = defaultdict(list)
        for rv, reviewer_login in s.execute(
            select(PRReview, Contributor.login).outerjoin(
                Contributor, PRReview.reviewer_id == Contributor.id
            )
        ).all():
            reviews_by_pr[rv.pr_id].append(
                {
                    "submitted_at": rv.submitted_at,
                    "state": rv.state,
                    "reviewer_login": reviewer_login,
                }
            )

        # Author login per contributor — needed because the metrics functions key off
        # author_login vs reviewer_login (not IDs).
        author_login: dict[int, str] = dict(s.execute(select(Contributor.id, Contributor.login)).all())

        # PRs by (author_id, repo_id, ym) — only merged
        buckets: dict[tuple[int | None, int, str], list[dict]] = defaultdict(list)
        prs_reviewed_by_contributor: dict[tuple[int, str], set[int]] = defaultdict(set)

        for pr in s.execute(
            select(PullRequest).where(PullRequest.merged_at.is_not(None))
        ).scalars():
            pr_ym = year_month(pr.merged_at)
            if pr_ym != ym:
                continue
            pr_dict = {
                "id": pr.id,
                "opened_at": pr.opened_at,
                "merged_at": pr.merged_at,
                "first_commit_at": commit_map.get(pr.id),
                "additions": pr.additions,
                "deletions": pr.deletions,
                "author_login": author_login.get(pr.author_id) if pr.author_id else None,
                "reviews": reviews_by_pr.get(pr.id, []),
            }
            buckets[(pr.author_id, pr.repo_id, pr_ym)].append(pr_dict)

            # prs_reviewed counter — count distinct PRs reviewed per non-author reviewer
            for rv in pr_dict["reviews"]:
                rl = rv.get("reviewer_login")
                if not rl or rl == pr_dict["author_login"]:
                    continue
                # Map login → contributor id (reverse author_login map; cheap enough at our scale)
                # If multiple contributors share a login (shouldn't), this is fine.
                pass  # filled in below

        # Build reverse map login → contributor_id
        login_to_id: dict[str, int] = {v: k for k, v in author_login.items()}
        for (_author_id, _repo_id, pr_ym), prs in buckets.items():
            for pr in prs:
                for rv in pr["reviews"]:
                    rl = rv.get("reviewer_login")
                    if not rl or rl == pr["author_login"]:
                        continue
                    rid = login_to_id.get(rl)
                    if rid:
                        prs_reviewed_by_contributor[(rid, pr_ym)].add(pr["id"])

        # Deployments per repo per month
        dep_counts: dict[tuple[int, str], int] = defaultdict(int)
        for d in s.execute(select(Deployment)).scalars():
            dep_counts[(d.repo_id, year_month(d.triggered_at))] += 1

        # Build per-bucket snapshot rows
        for (contributor_id, repo_id, snap_ym), prs in buckets.items():
            lt_p50, lt_p75 = lt.aggregate(prs)
            ct_agg = ct.aggregate(prs)
            size = sz.aggregate(prs)
            cov = rc.aggregate(prs)
            ttfr_p50 = ttfr.aggregate(prs)
            prs_reviewed = (
                len(prs_reviewed_by_contributor.get((contributor_id, snap_ym), set()))
                if contributor_id
                else 0
            )

            values = dict(
                contributor_id=contributor_id,
                repo_id=repo_id,
                year_month=snap_ym,
                prs_merged=len(prs),
                prs_reviewed=prs_reviewed,
                lead_time_p50_hours=lt_p50,
                lead_time_p75_hours=lt_p75,
                deployment_count=dep_counts.get((repo_id, snap_ym), 0) if contributor_id is None else 0,
                median_pr_size_lines=size,
                review_coverage_pct=cov,
                median_time_to_first_review_hours=ttfr_p50,
                median_pr_cycle_time_hours=ct_agg["total_p50"],
                median_pickup_time_hours=ct_agg["pickup_p50"],
                median_review_time_hours=ct_agg["review_p50"],
                median_merge_time_hours=ct_agg["merge_p50"],
                is_finalized=False,
            )
            update_set = {k: v for k, v in values.items() if k not in {
                "contributor_id", "repo_id", "year_month", "is_finalized"
            }}

            stmt = (
                pg_insert(ContributorMonthSnapshot)
                .values(**values)
                .on_conflict_do_update(
                    constraint="uq_snapshot_contrib_repo_month",
                    set_=update_set,
                    where=ContributorMonthSnapshot.is_finalized.is_(False),
                )
            )
            s.execute(stmt)
            written += 1

        # Repo-level deployment rows (contributor_id NULL)
        for (repo_id, dep_ym), cnt in dep_counts.items():
            if dep_ym != ym:
                continue
            stmt = (
                pg_insert(ContributorMonthSnapshot)
                .values(
                    contributor_id=None,
                    repo_id=repo_id,
                    year_month=ym,
                    prs_merged=0,
                    deployment_count=cnt,
                    is_finalized=False,
                )
                .on_conflict_do_update(
                    constraint="uq_snapshot_contrib_repo_month",
                    set_={"deployment_count": cnt},
                    where=ContributorMonthSnapshot.is_finalized.is_(False),
                )
            )
            s.execute(stmt)

    log.info("Rebuilt %d snapshot rows for %s", written, ym)
    return written


def finalize_prior_month() -> int:
    """Mark prior month's snapshots as finalized; no further recalculation will touch them."""
    now = datetime.now(timezone.utc)
    if now.month == 1:
        prior_ym = f"{now.year - 1:04d}-12"
    else:
        prior_ym = f"{now.year:04d}-{now.month - 1:02d}"
    with session_scope() as s:
        rows = s.execute(
            select(ContributorMonthSnapshot).where(
                ContributorMonthSnapshot.year_month == prior_ym,
                ContributorMonthSnapshot.is_finalized.is_(False),
            )
        ).scalars().all()
        for r in rows:
            r.is_finalized = True
    log.info("Finalized %d snapshot rows for %s", len(rows), prior_ym)
    return len(rows)


def last_sync_status() -> dict:
    from .models import DataSource

    with session_scope() as s:
        entry = s.execute(
            select(SyncLog).order_by(SyncLog.started_at.desc()).limit(1)
        ).scalar_one_or_none()
        if not entry:
            return {"status": "never_run"}

        current_source_label: str | None = None
        if entry.current_source_id:
            ds = s.get(DataSource, entry.current_source_id)
            if ds:
                current_source_label = f"{ds.source}/{ds.org_or_group}"

        return {
            "status": entry.status,
            "started_at": entry.started_at.isoformat(),
            "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
            "repos_synced": entry.repos_synced,
            "prs_synced": entry.prs_synced,
            "error": entry.error,
            "total_repos": entry.total_repos or 0,
            "repos_done": entry.repos_done or 0,
            "current_source_id": entry.current_source_id,
            "current_source_label": current_source_label,
            "current_repo": entry.current_repo,
            "cancel_requested": bool(entry.cancel_requested),
            "events": list(entry.events or []),
        }
