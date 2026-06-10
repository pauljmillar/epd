"""GitLab collector — REST v4.

Mirrors the GitHub collector's dataclass interface (RepoRef, PRRecord, ReviewRecord,
DeploymentRecord) so the sync orchestrator can treat both sources uniformly.

GitLab terminology mapping:
  - Project  → repository
  - Merge Request (MR) → pull request
  - Notes (non-system, non-author) → review events. GitLab's formal "approvals" feature is
    Premium-only, so we use notes as a proxy. State is "COMMENTED" except when the note's
    body matches an approval keyword (rare; ignored for v1).
  - Tags or merges to default branch → deployments (same as GitHub).

Known gaps vs GitHub (documented in README "GitLab limitations"):
  - additions/deletions per MR: REST list endpoint doesn't include them, and per-MR fetch
    of /diffs is expensive. We grab them from the MR detail when present (newer GitLab
    versions populate them), otherwise default to 0. PR Size metric may be 0 for older
    GitLab instances.
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from ..config import settings

log = logging.getLogger(__name__)

GITLAB_API = "https://gitlab.com/api/v4"


@dataclass
class RepoRef:
    source_id: str
    name: str
    full_name: str  # group/subgroup/project — GitLab "path_with_namespace"
    default_branch: str


@dataclass
class ReviewRecord:
    source_id: str
    reviewer_login: str | None
    reviewer_source_id: str | None
    submitted_at: datetime
    state: str  # COMMENTED | APPROVED


@dataclass
class PRRecord:
    source_id: str
    number: int  # MR iid
    title: str
    url: str
    author_login: str | None
    author_source_id: str | None
    opened_at: datetime
    merged_at: datetime | None
    closed_at: datetime | None
    additions: int
    deletions: int
    base_branch: str
    is_draft: bool
    first_commit_at: datetime | None
    reviews: list[ReviewRecord]
    body: str | None = None
    merge_commit_body: str | None = None


@dataclass
class DeploymentRecord:
    triggered_at: datetime
    signal_type: str
    ref: str


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class GitLabClient:
    def __init__(self, token: str, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(
            headers={
                "PRIVATE-TOKEN": token,
                "User-Agent": "epd/0.1",
            },
            timeout=30.0,
            transport=transport,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        for attempt in range(5):
            r = await self._client.request(method, url, **kw)
            # GitLab returns 429 with Retry-After on rate limit.
            if r.status_code == 429:
                wait_s = int(r.headers.get("Retry-After", "5"))
                wait = min(wait_s * (2**attempt), 600)
                log.warning("GitLab rate limited; sleeping %ds (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError("Exhausted GitLab retry attempts")

    async def _paged(self, url: str, params: dict[str, Any] | None = None) -> list[dict]:
        out: list[dict] = []
        page = 1
        params = dict(params or {})
        while True:
            params["page"] = page
            params["per_page"] = 100
            r = await self._request("GET", url, params=params)
            data = r.json()
            if not isinstance(data, list) or not data:
                break
            out.extend(data)
            # GitLab paginates via Link header; X-Next-Page header is also reliable.
            next_page = r.headers.get("X-Next-Page", "").strip()
            if not next_page:
                break
            page = int(next_page)
        return out

    async def list_group_projects(self, group: str) -> list[RepoRef]:
        """All projects in a group (including subgroups), excluding archived."""
        encoded = quote(group, safe="")
        data = await self._paged(
            f"{GITLAB_API}/groups/{encoded}/projects",
            {"include_subgroups": "true", "archived": "false"},
        )
        return [
            RepoRef(
                source_id=str(p["id"]),
                name=p["name"],
                full_name=p["path_with_namespace"],
                default_branch=p.get("default_branch") or "main",
            )
            for p in data
        ]

    async def list_merged_mrs(self, repo: RepoRef, since: datetime) -> list[PRRecord]:
        """All merged MRs in `repo` updated since `since`, with author + commits[0] + notes."""
        # `with_stats=true` makes the list endpoint return additions/deletions per MR (older
        # GitLab instances don't populate those on the per-MR detail). One round trip vs N.
        list_data = await self._paged(
            f"{GITLAB_API}/projects/{repo.source_id}/merge_requests",
            {
                "state": "merged",
                "order_by": "updated_at",
                "sort": "desc",
                "updated_after": since.isoformat().replace("+00:00", "Z"),
                "scope": "all",
                "with_stats": "true",
            },
        )

        out: list[PRRecord] = []
        for mr in list_data:
            iid = mr["iid"]
            # Detail call — gives `description`, sometimes `additions`/`deletions`.
            detail_r = await self._request(
                "GET",
                f"{GITLAB_API}/projects/{repo.source_id}/merge_requests/{iid}",
            )
            detail = detail_r.json()

            # Commits — earliest authored_date for lead time.
            commits = await self._paged(
                f"{GITLAB_API}/projects/{repo.source_id}/merge_requests/{iid}/commits"
            )
            first_commit_at = None
            if commits:
                # GitLab returns commits in reverse-chronological order; take the oldest.
                dates = [
                    _parse_dt(c.get("authored_date") or c.get("committed_date"))
                    for c in commits
                ]
                dates = [d for d in dates if d is not None]
                if dates:
                    first_commit_at = min(dates)

            # Notes — treat any non-system note from a non-author as a "review event".
            notes = await self._paged(
                f"{GITLAB_API}/projects/{repo.source_id}/merge_requests/{iid}/notes",
                {"sort": "asc", "order_by": "created_at"},
            )
            reviews = _notes_to_reviews(notes, (detail.get("author") or {}).get("username"))

            # The merge commit body — best-effort: GitLab embeds it in `merge_commit_sha`
            # but we'd need a separate /commits/{sha} call. Skipping for v1; AI detection
            # falls back to the MR description.
            merge_commit_body = None

            author = detail.get("author") or {}
            # Prefer additions/deletions from the list item (populated by with_stats=true
            # on older GitLab versions) and fall back to detail when the list omitted them.
            additions = _first_nonzero_int(mr.get("additions"), detail.get("additions"))
            deletions = _first_nonzero_int(mr.get("deletions"), detail.get("deletions"))
            out.append(
                PRRecord(
                    source_id=str(detail.get("id") or iid),
                    number=int(iid),
                    title=detail.get("title", "") or "",
                    url=detail.get("web_url", "") or "",
                    author_login=author.get("username"),
                    author_source_id=str(author["id"]) if author.get("id") else None,
                    opened_at=_parse_dt(detail["created_at"]) or datetime.now(timezone.utc),
                    merged_at=_parse_dt(detail.get("merged_at")),
                    closed_at=_parse_dt(detail.get("closed_at")),
                    additions=additions,
                    deletions=deletions,
                    base_branch=detail.get("target_branch") or "main",
                    is_draft=bool(detail.get("draft") or detail.get("work_in_progress")),
                    first_commit_at=first_commit_at,
                    reviews=reviews,
                    body=detail.get("description"),
                    merge_commit_body=merge_commit_body,
                )
            )
        return out

    async def list_deployments(self, repo: RepoRef, since: datetime) -> list[DeploymentRecord]:
        if settings.deployment_tag_pattern:
            return await self._tag_deployments(repo, since)
        return await self._branch_merge_deployments(repo, since)

    async def _branch_merge_deployments(
        self, repo: RepoRef, since: datetime
    ) -> list[DeploymentRecord]:
        branch = settings.deployment_branch or repo.default_branch
        data = await self._paged(
            f"{GITLAB_API}/projects/{repo.source_id}/repository/commits",
            {
                "ref_name": branch,
                "since": since.isoformat().replace("+00:00", "Z"),
            },
        )
        out: list[DeploymentRecord] = []
        for c in data:
            date = _parse_dt(c.get("committed_date") or c.get("authored_date"))
            if date is None:
                continue
            out.append(
                DeploymentRecord(triggered_at=date, signal_type="branch_merge", ref=c["id"])
            )
        return out

    async def _tag_deployments(
        self, repo: RepoRef, since: datetime
    ) -> list[DeploymentRecord]:
        pattern = settings.deployment_tag_pattern or "v*"
        data = await self._paged(f"{GITLAB_API}/projects/{repo.source_id}/repository/tags")
        out: list[DeploymentRecord] = []
        for tag in data:
            if not fnmatch.fnmatch(tag["name"], pattern):
                continue
            commit = tag.get("commit") or {}
            date = _parse_dt(commit.get("committed_date") or commit.get("authored_date"))
            if date is None or date < since:
                continue
            out.append(
                DeploymentRecord(triggered_at=date, signal_type="tag", ref=tag["name"])
            )
        return out


def _notes_to_reviews(notes: list[dict], author_username: str | None) -> list[ReviewRecord]:
    out: list[ReviewRecord] = []
    for n in notes:
        if n.get("system"):
            continue  # system notes (assignee change, etc.) — not reviews
        a = n.get("author") or {}
        username = a.get("username")
        if not username or username == author_username:
            continue
        ts = _parse_dt(n.get("created_at"))
        if ts is None:
            continue
        body = (n.get("body") or "").lower()
        state = "APPROVED" if "approved" in body or "lgtm" in body else "COMMENTED"
        out.append(
            ReviewRecord(
                source_id=str(n.get("id")),
                reviewer_login=username,
                reviewer_source_id=str(a["id"]) if a.get("id") else None,
                submitted_at=ts,
                state=state,
            )
        )
    return out


def _first_nonzero_int(*values: object) -> int:
    """Return the first integer-convertible value that is truthy (non-zero). Falls back to
    0 if none are. Used to prefer the with_stats list value over the detail value when the
    detail one is 0 (older GitLab)."""
    for v in values:
        if v is None:
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n:
            return n
    return 0


def backfill_since() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=30 * settings.backfill_months)
