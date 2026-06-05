"""Build contributor_month_snapshots from raw PRs/commits/deployments.

BRD §8: monthly snapshots are immutable once finalized. The current (incomplete) month is
recalculated nightly; prior months are recalculated only until finalization runs on the 1st.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import session_scope
from .metrics import lead_time as lt
from .metrics.common import year_month
from .models import (
    ContributorMonthSnapshot,
    Deployment,
    PRCommit,
    PullRequest,
    SyncLog,
)

log = logging.getLogger(__name__)


def _current_year_month() -> str:
    return year_month(datetime.now(timezone.utc))


def rebuild_current_period() -> int:
    """Rebuild the current month's per-contributor-per-repo snapshots."""
    ym = _current_year_month()
    return rebuild_month(ym)


def rebuild_month(ym: str) -> int:
    """Rebuild snapshots for a given YYYY-MM. Skips rows marked is_finalized."""
    written = 0
    with session_scope() as s:
        # First-commit lookup per PR
        commit_map: dict[int, datetime] = {}
        for row in s.execute(select(PRCommit.pr_id, PRCommit.authored_at)).all():
            existing = commit_map.get(row.pr_id)
            if existing is None or row.authored_at < existing:
                commit_map[row.pr_id] = row.authored_at

        # Group PRs by (contributor_id, repo_id, ym)
        buckets: dict[tuple[int | None, int, str], list[dict]] = defaultdict(list)
        for pr in s.execute(select(PullRequest).where(PullRequest.merged_at.is_not(None))).scalars():
            pr_ym = year_month(pr.merged_at)
            if pr_ym != ym:
                continue
            buckets[(pr.author_id, pr.repo_id, pr_ym)].append(
                {
                    "opened_at": pr.opened_at,
                    "merged_at": pr.merged_at,
                    "first_commit_at": commit_map.get(pr.id),
                }
            )

        # Deployments per repo per month
        dep_counts: dict[tuple[int, str], int] = defaultdict(int)
        for d in s.execute(select(Deployment)).scalars():
            dep_counts[(d.repo_id, year_month(d.triggered_at))] += 1

        for (contributor_id, repo_id, _), prs in buckets.items():
            p50, p75 = lt.aggregate(prs)
            stmt = (
                pg_insert(ContributorMonthSnapshot)
                .values(
                    contributor_id=contributor_id,
                    repo_id=repo_id,
                    year_month=ym,
                    prs_merged=len(prs),
                    prs_reviewed=0,  # filled in below at the contributor level
                    lead_time_p50_hours=p50,
                    lead_time_p75_hours=p75,
                    deployment_count=dep_counts.get((repo_id, ym), 0) if contributor_id is None else 0,
                    is_finalized=False,
                )
                .on_conflict_do_update(
                    constraint="uq_snapshot_contrib_repo_month",
                    set_={
                        "prs_merged": len(prs),
                        "lead_time_p50_hours": p50,
                        "lead_time_p75_hours": p75,
                    },
                    where=ContributorMonthSnapshot.is_finalized.is_(False),
                )
            )
            s.execute(stmt)
            written += 1

        # Repo-level deployment rows (contributor_id NULL) so deploys are queryable independent of authors
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
    with session_scope() as s:
        entry = s.execute(
            select(SyncLog).order_by(SyncLog.started_at.desc()).limit(1)
        ).scalar_one_or_none()
        if not entry:
            return {"status": "never_run"}
        return {
            "status": entry.status,
            "started_at": entry.started_at.isoformat(),
            "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
            "repos_synced": entry.repos_synced,
            "prs_synced": entry.prs_synced,
            "error": entry.error,
        }
