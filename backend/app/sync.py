"""Sync orchestration — pulls from configured collectors (GitHub, GitLab) and persists.

The two collectors expose structurally-compatible dataclasses (RepoRef, PRRecord,
ReviewRecord, DeploymentRecord) so the persistence layer is source-agnostic — we just
tag the rows with `source` ('github' | 'gitlab').
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import ai_attribution
from .collectors.github import GitHubClient
from .collectors.github import backfill_since as github_backfill_since
from .collectors.gitlab import GitLabClient
from .collectors.gitlab import backfill_since as gitlab_backfill_since
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


# --- Source-agnostic persist helpers -----------------------------------------


def _upsert_contributor(
    session: Session, source: str, login: str | None, source_id: str | None
) -> Contributor | None:
    if not login or not source_id:
        return None
    existing = session.execute(
        select(Contributor).where(
            Contributor.source == source, Contributor.source_id == source_id
        )
    ).scalar_one_or_none()
    if existing:
        if existing.login != login:
            existing.login = login
        return existing
    c = Contributor(source=source, source_id=source_id, login=login, display_name=login)
    session.add(c)
    session.flush()
    return c


def _upsert_repo(session: Session, source: str, ref: Any) -> Repository:
    existing = session.execute(
        select(Repository).where(
            Repository.source == source, Repository.source_id == ref.source_id
        )
    ).scalar_one_or_none()
    if existing:
        existing.name = ref.name
        existing.full_name = ref.full_name
        existing.default_branch = ref.default_branch
        return existing
    r = Repository(
        source=source,
        source_id=ref.source_id,
        name=ref.name,
        full_name=ref.full_name,
        default_branch=ref.default_branch,
    )
    session.add(r)
    session.flush()
    return r


def _persist_pr(session: Session, source: str, repo: Repository, pr: Any) -> None:
    if pr.author_login and pr.author_login in settings.excluded_user_set:
        return
    author = _upsert_contributor(session, source, pr.author_login, pr.author_source_id)
    ai_assisted, ai_tool = ai_attribution.detect(pr.merge_commit_body, pr.body)

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
            ai_assisted=ai_assisted,
            ai_tool=ai_tool,
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
                "ai_assisted": ai_assisted,
                "ai_tool": ai_tool,
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
        reviewer = _upsert_contributor(session, source, rv.reviewer_login, rv.reviewer_source_id)
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


def _persist_deployment(session: Session, repo: Repository, dep: Any) -> None:
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


# --- Per-source runners ------------------------------------------------------


class _SourceCollector(Protocol):
    """Structural type both GitHub/GitLab clients satisfy."""

    async def __aenter__(self) -> "_SourceCollector": ...
    async def __aexit__(self, *exc: Any) -> None: ...


async def _run_one_source(
    source: str,
    collector: Any,
    list_repos_coro,
    list_prs_coro,
    list_deps_coro,
    since: datetime,
) -> tuple[int, int]:
    """Common loop. Returns (repos_synced, prs_synced)."""
    repos_synced = 0
    prs_synced = 0

    with session_scope() as s:
        untracked = {
            row[0]
            for row in s.execute(
                select(Repository.full_name).where(
                    Repository.source == source, Repository.is_tracked.is_(False)
                )
            ).all()
        }
    excluded = settings.excluded_repo_set

    refs = await list_repos_coro
    log.info("[%s] found %d repos", source, len(refs))

    for ref in refs:
        if ref.name in excluded or ref.full_name in excluded:
            continue
        if ref.full_name in untracked:
            log.info("[%s] skipping untracked %s", source, ref.full_name)
            continue
        try:
            prs = await list_prs_coro(ref, since)
            deps = await list_deps_coro(ref, since)
        except Exception as e:  # noqa: BLE001
            log.exception("[%s] sync failed for %s: %s", source, ref.full_name, e)
            continue
        with session_scope() as s:
            repo = _upsert_repo(s, source, ref)
            for pr in prs:
                _persist_pr(s, source, repo, pr)
                prs_synced += 1
            for d in deps:
                _persist_deployment(s, repo, d)
        repos_synced += 1
        log.info("[%s] synced %s: %d PRs, %d deployments", source, ref.full_name, len(prs), len(deps))

    return repos_synced, prs_synced


async def _run_github() -> tuple[int, int]:
    since = github_backfill_since()
    async with GitHubClient(settings.github_token) as gh:
        return await _run_one_source(
            "github",
            gh,
            gh.list_org_repos(settings.github_org),
            gh.list_merged_prs,
            gh.list_deployments,
            since,
        )


async def _run_gitlab() -> tuple[int, int]:
    since = gitlab_backfill_since()
    async with GitLabClient(settings.gitlab_token) as gl:
        return await _run_one_source(
            "gitlab",
            gl,
            gl.list_group_projects(settings.gitlab_group),
            gl.list_merged_mrs,
            gl.list_deployments,
            since,
        )


async def run_sync() -> dict:
    """One sync pass across every configured source."""
    sources_to_run: list[tuple[str, Any]] = []
    if settings.github_token and settings.github_org:
        sources_to_run.append(("github", _run_github))
    if settings.gitlab_token and settings.gitlab_group:
        sources_to_run.append(("gitlab", _run_gitlab))

    if not sources_to_run:
        log.warning("No source configured (need GITHUB_TOKEN+GITHUB_ORG or GITLAB_TOKEN+GITLAB_GROUP)")
        return {"status": "skipped", "reason": "no source configured"}

    started = datetime.now(timezone.utc)
    with session_scope() as s:
        log_entry = SyncLog(started_at=started, status="running")
        s.add(log_entry)
        s.flush()
        log_id = log_entry.id

    total_repos = 0
    total_prs = 0
    err: str | None = None

    try:
        for source_name, runner in sources_to_run:
            log.info("Running sync for %s", source_name)
            r, p = await runner()
            total_repos += r
            total_prs += p
    except Exception as e:  # noqa: BLE001
        err = str(e)[:2000]
        log.exception("Sync failed: %s", e)

    with session_scope() as s:
        entry = s.get(SyncLog, log_id)
        if entry:
            entry.completed_at = datetime.now(timezone.utc)
            entry.repos_synced = total_repos
            entry.prs_synced = total_prs
            entry.status = "failed" if err else "completed"
            entry.error = err

    from .snapshots import rebuild_current_period

    rebuild_current_period()

    from .api.metrics import cache_invalidate_all

    cache_invalidate_all()

    return {
        "status": "failed" if err else "completed",
        "repos_synced": total_repos,
        "prs_synced": total_prs,
        "error": err,
    }


def run_sync_sync() -> dict:
    return asyncio.run(run_sync())
