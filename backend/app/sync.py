"""Sync orchestration — iterates over active data_sources rows and persists each one.

The two collectors expose structurally-compatible dataclasses (RepoRef, PRRecord,
ReviewRecord, DeploymentRecord) so the persistence layer is source-agnostic — we tag rows
with `source` ('github' | 'gitlab') plus the originating `data_source_id` for clean
scope-by-source admin actions (purge, soft-remove).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

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
    DataSource,
    Deployment,
    PRCommit,
    PRReview,
    PullRequest,
    Repository,
    SyncLog,
)
from .sources import get_active_sources

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


def _upsert_repo(
    session: Session, source: str, ref: Any, data_source_id: int | None = None
) -> Repository:
    existing = session.execute(
        select(Repository).where(
            Repository.source == source, Repository.source_id == ref.source_id
        )
    ).scalar_one_or_none()
    if existing:
        existing.name = ref.name
        existing.full_name = ref.full_name
        existing.default_branch = ref.default_branch
        if data_source_id is not None and existing.data_source_id != data_source_id:
            existing.data_source_id = data_source_id
        return existing
    r = Repository(
        source=source,
        source_id=ref.source_id,
        name=ref.name,
        full_name=ref.full_name,
        default_branch=ref.default_branch,
        data_source_id=data_source_id,
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


# --- Progress + event helpers (added in Phase SP) ----------------------------

# How many events to keep in the ring buffer. Anything older falls off.
_EVENT_BUFFER_SIZE = 50


def _progress(log_id: int, **fields: Any) -> None:
    """Patch the given sync_log row. Short, isolated transaction so concurrent reads see
    the new state quickly."""
    with session_scope() as s:
        entry = s.get(SyncLog, log_id)
        if entry is None:
            return
        for k, v in fields.items():
            setattr(entry, k, v)


def _emit(log_id: int, level: str, msg: str) -> None:
    """Append an event to the ring buffer on the given sync_log row, truncating to the
    last _EVENT_BUFFER_SIZE entries."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "msg": msg,
    }
    with session_scope() as s:
        entry = s.get(SyncLog, log_id)
        if entry is None:
            return
        # SQLAlchemy JSONB lists must be reassigned (not mutated in place) for the change
        # to be detected. Slice off the head if we exceed the buffer size.
        next_events = (entry.events or []) + [event]
        if len(next_events) > _EVENT_BUFFER_SIZE:
            next_events = next_events[-_EVENT_BUFFER_SIZE:]
        entry.events = next_events


def _is_cancelled(log_id: int) -> bool:
    """Check the cancel_requested flag — called between repos so cancellation lands at a
    safe boundary (after the in-flight DB writes for the previous repo commit)."""
    with session_scope() as s:
        entry = s.get(SyncLog, log_id)
        return bool(entry and entry.cancel_requested)


# --- Per-source runners ------------------------------------------------------


async def _run_one_source(ds: DataSource, log_id: int) -> tuple[int, int, bool]:
    """Sync one data_source row. Returns (repos_synced, prs_synced, cancelled)."""
    repos_synced = 0
    prs_synced = 0

    if ds.source == "github":
        since = github_backfill_since()
        client_cm = GitHubClient(ds.token)
    elif ds.source == "gitlab":
        since = gitlab_backfill_since()
        client_cm = GitLabClient(ds.token)
    else:
        log.warning("Unknown source %r on data_source %s, skipping", ds.source, ds.id)
        _emit(log_id, "warning", f"Unknown source {ds.source!r}, skipping")
        return 0, 0, False

    _progress(log_id, current_source_id=ds.id)
    _emit(log_id, "info", f"Starting {ds.source}/{ds.org_or_group}")

    async with client_cm as client:
        if ds.source == "github":
            refs = await client.list_org_repos(ds.org_or_group)
        else:
            refs = await client.list_group_projects(ds.org_or_group)
        log.info("[%s/%s] found %d repos", ds.source, ds.org_or_group, len(refs))
        _progress(log_id, total_repos=len(refs))
        _emit(log_id, "info", f"Found {len(refs)} repos in {ds.org_or_group}")

        with session_scope() as s:
            untracked = {
                row[0]
                for row in s.execute(
                    select(Repository.full_name).where(
                        Repository.source == ds.source, Repository.is_tracked.is_(False)
                    )
                ).all()
            }
        excluded = settings.excluded_repo_set

        list_prs = (
            client.list_merged_prs if ds.source == "github" else client.list_merged_mrs
        )
        list_deps = client.list_deployments

        for index, ref in enumerate(refs, start=1):
            if _is_cancelled(log_id):
                _emit(log_id, "warning", f"Cancelled at {index - 1}/{len(refs)}")
                return repos_synced, prs_synced, True

            if ref.name in excluded or ref.full_name in excluded:
                continue
            if ref.full_name in untracked:
                log.info("[%s/%s] skipping untracked %s", ds.source, ds.org_or_group, ref.full_name)
                continue

            _progress(log_id, current_repo=ref.full_name)
            _emit(log_id, "info", f"Syncing {ref.full_name} ({index}/{len(refs)})")
            try:
                prs = await list_prs(ref, since)
                deps = await list_deps(ref, since)
            except Exception as e:  # noqa: BLE001
                log.exception(
                    "[%s/%s] sync failed for %s: %s",
                    ds.source, ds.org_or_group, ref.full_name, e,
                )
                _emit(log_id, "error", f"{ref.full_name} failed: {e!r}")
                continue
            with session_scope() as s:
                repo = _upsert_repo(s, ds.source, ref, data_source_id=ds.id)
                for pr in prs:
                    _persist_pr(s, ds.source, repo, pr)
                    prs_synced += 1
                for d in deps:
                    _persist_deployment(s, repo, d)
            repos_synced += 1
            log.info(
                "[%s/%s] synced %s: %d PRs, %d deployments",
                ds.source, ds.org_or_group, ref.full_name, len(prs), len(deps),
            )
            _progress(log_id, repos_done=repos_synced)
            _emit(
                log_id, "info",
                f"Done {ref.full_name}: {len(prs)} PRs, {len(deps)} deployments",
            )

    # Mark this source's sync time on completion of its loop.
    with session_scope() as s:
        row = s.get(DataSource, ds.id)
        if row:
            row.last_synced_at = datetime.now(timezone.utc)

    return repos_synced, prs_synced, False


async def run_sync(only_data_source_id: int | None = None) -> dict:
    """Sync every active data_source (or just one if `only_data_source_id` is given)."""
    sources = list(get_active_sources())
    if only_data_source_id is not None:
        sources = [s for s in sources if s.id == only_data_source_id]
    if not sources:
        log.warning("No active data_sources to sync")
        return {"status": "skipped", "reason": "no active data_sources"}

    started = datetime.now(timezone.utc)
    with session_scope() as s:
        log_entry = SyncLog(started_at=started, status="running")
        s.add(log_entry)
        s.flush()
        log_id = log_entry.id

    total_repos = 0
    total_prs = 0
    err: str | None = None
    cancelled = False

    try:
        for ds in sources:
            log.info("Running sync for data_source %s/%s", ds.source, ds.org_or_group)
            r, p, src_cancelled = await _run_one_source(ds, log_id)
            total_repos += r
            total_prs += p
            if src_cancelled:
                cancelled = True
                break
    except Exception as e:  # noqa: BLE001
        err = str(e)[:2000]
        log.exception("Sync failed: %s", e)
        _emit(log_id, "error", f"Sync failed: {e!r}")

    if cancelled:
        final_status = "cancelled"
    elif err:
        final_status = "failed"
    else:
        final_status = "completed"

    with session_scope() as s:
        entry = s.get(SyncLog, log_id)
        if entry:
            entry.completed_at = datetime.now(timezone.utc)
            entry.repos_synced = total_repos
            entry.prs_synced = total_prs
            entry.status = final_status
            entry.error = err
            entry.current_repo = None
            entry.current_source_id = None
    _emit(log_id, "info", f"Sync {final_status}: {total_repos} repos, {total_prs} PRs")

    from .snapshots import rebuild_current_period

    rebuild_current_period()

    from .api.metrics import cache_invalidate_all

    cache_invalidate_all()

    return {
        "status": final_status,
        "repos_synced": total_repos,
        "prs_synced": total_prs,
        "error": err,
    }


def run_sync_sync(only_data_source_id: int | None = None) -> dict:
    return asyncio.run(run_sync(only_data_source_id=only_data_source_id))
