"""Sync orchestration — pulls from GitHub collector and persists to DB."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .collectors.github import (
    DeploymentRecord,
    GitHubClient,
    PRRecord,
    RepoRef,
    backfill_since,
)
from .config import settings
from .db import session_scope
from .models import (
    Contributor,
    Deployment,
    PRCommit,
    PRReview,
    PullRequest,
    Repository,
    SyncLog,
)

log = logging.getLogger(__name__)


def _upsert_contributor(
    session: Session, login: str | None, source_id: str | None
) -> Contributor | None:
    if not login or not source_id:
        return None
    existing = session.execute(
        select(Contributor).where(Contributor.source == "github", Contributor.source_id == source_id)
    ).scalar_one_or_none()
    if existing:
        if existing.login != login:
            existing.login = login
        return existing
    c = Contributor(source="github", source_id=source_id, login=login, display_name=login)
    session.add(c)
    session.flush()
    return c


def _upsert_repo(session: Session, ref: RepoRef) -> Repository:
    existing = session.execute(
        select(Repository).where(
            Repository.source == "github", Repository.source_id == ref.source_id
        )
    ).scalar_one_or_none()
    if existing:
        existing.name = ref.name
        existing.full_name = ref.full_name
        existing.default_branch = ref.default_branch
        return existing
    r = Repository(
        source="github",
        source_id=ref.source_id,
        name=ref.name,
        full_name=ref.full_name,
        default_branch=ref.default_branch,
    )
    session.add(r)
    session.flush()
    return r


def _persist_pr(session: Session, repo: Repository, pr: PRRecord) -> None:
    if pr.author_login and pr.author_login in settings.excluded_user_set:
        return
    author = _upsert_contributor(session, pr.author_login, pr.author_source_id)

    stmt = (
        pg_insert(PullRequest)
        .values(
            repo_id=repo.id,
            source_id=pr.source_id,
            number=pr.number,
            author_id=author.id if author else None,
            title=pr.title[:1024],
            url=pr.url[:1024] if pr.url else None,
            opened_at=pr.opened_at,
            merged_at=pr.merged_at,
            closed_at=pr.closed_at,
            additions=pr.additions,
            deletions=pr.deletions,
            base_branch=pr.base_branch[:128],
            is_draft=pr.is_draft,
        )
        .on_conflict_do_update(
            constraint="uq_pr_repo_number",
            set_={
                "title": pr.title[:1024],
                "merged_at": pr.merged_at,
                "closed_at": pr.closed_at,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "is_draft": pr.is_draft,
                "author_id": author.id if author else None,
            },
        )
        .returning(PullRequest.id)
    )
    pr_id = session.execute(stmt).scalar_one()

    if pr.first_commit_at:
        session.execute(
            pg_insert(PRCommit)
            .values(
                pr_id=pr_id,
                sha=f"first-{pr.source_id}",
                authored_at=pr.first_commit_at,
                committed_at=pr.first_commit_at,
            )
            .on_conflict_do_nothing(constraint="uq_commit_pr_sha")
        )

    for rv in pr.reviews:
        reviewer = _upsert_contributor(session, rv.reviewer_login, rv.reviewer_source_id)
        session.execute(
            pg_insert(PRReview)
            .values(
                pr_id=pr_id,
                reviewer_id=reviewer.id if reviewer else None,
                source_id=rv.source_id,
                submitted_at=rv.submitted_at,
                state=rv.state,
            )
            .on_conflict_do_nothing(constraint="uq_review_source")
        )


def _persist_deployment(session: Session, repo: Repository, dep: DeploymentRecord) -> None:
    session.execute(
        pg_insert(Deployment)
        .values(
            repo_id=repo.id,
            triggered_at=dep.triggered_at,
            signal_type=dep.signal_type,
            ref=dep.ref[:256],
        )
        .on_conflict_do_nothing(constraint="uq_dep_ref")
    )


async def run_sync() -> dict:
    """One sync pass: pull all org repos, fetch merged PRs + deployments since backfill window."""
    if not settings.github_token or not settings.github_org:
        log.warning("GitHub not configured; skipping sync")
        return {"status": "skipped", "reason": "github not configured"}

    started = datetime.now(timezone.utc)
    with session_scope() as s:
        log_entry = SyncLog(started_at=started, status="running")
        s.add(log_entry)
        s.flush()
        log_id = log_entry.id

    repos_synced = 0
    prs_synced = 0
    err: str | None = None

    try:
        async with GitHubClient(settings.github_token) as gh:
            refs = await gh.list_org_repos(settings.github_org)
            log.info("Found %d repos in org %s", len(refs), settings.github_org)
            since = backfill_since()
            excluded = settings.excluded_repo_set

            for ref in refs:
                if ref.name in excluded or ref.full_name in excluded:
                    continue
                try:
                    prs = await gh.list_merged_prs(ref, since)
                    deps = await gh.list_deployments(ref, since)
                except Exception as e:  # noqa: BLE001
                    log.exception("Failed to sync %s: %s", ref.full_name, e)
                    continue

                with session_scope() as s:
                    repo = _upsert_repo(s, ref)
                    for pr in prs:
                        _persist_pr(s, repo, pr)
                        prs_synced += 1
                    for d in deps:
                        _persist_deployment(s, repo, d)
                repos_synced += 1
                log.info(
                    "Synced %s: %d PRs, %d deployments", ref.full_name, len(prs), len(deps)
                )
    except Exception as e:  # noqa: BLE001
        err = str(e)[:2000]
        log.exception("Sync failed: %s", e)

    with session_scope() as s:
        entry = s.get(SyncLog, log_id)
        if entry:
            entry.completed_at = datetime.now(timezone.utc)
            entry.repos_synced = repos_synced
            entry.prs_synced = prs_synced
            entry.status = "failed" if err else "completed"
            entry.error = err

    # Snapshot recalculation after sync
    from .snapshots import rebuild_current_period

    rebuild_current_period()

    return {
        "status": "failed" if err else "completed",
        "repos_synced": repos_synced,
        "prs_synced": prs_synced,
        "error": err,
    }


def run_sync_sync() -> dict:
    """Thread-safe wrapper for APScheduler."""
    return asyncio.run(run_sync())
