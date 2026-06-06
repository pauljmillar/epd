"""GitHub collector.

Uses GraphQL v4 for PR + reviews + first commit in one round trip; REST v3 for repo
listing and tag-based deployments. Cursor pagination, exponential backoff on secondary
rate limits.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"


@dataclass
class RepoRef:
    source_id: str
    name: str
    full_name: str
    default_branch: str


@dataclass
class PRRecord:
    source_id: str
    number: int
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
class ReviewRecord:
    source_id: str
    reviewer_login: str | None
    reviewer_source_id: str | None
    submitted_at: datetime
    state: str


@dataclass
class DeploymentRecord:
    triggered_at: datetime
    signal_type: str
    ref: str


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class GitHubClient:
    def __init__(self, token: str, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "epd/0.1",
            },
            timeout=30.0,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        for attempt in range(5):
            r = await self._client.request(method, url, **kw)
            if r.status_code in (403, 429) and "rate limit" in r.text.lower():
                wait = min(60 * (2**attempt), 600)
                log.warning("Rate limited, sleeping %ds (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError("Exhausted GitHub retry attempts")

    async def list_org_repos(self, org: str) -> list[RepoRef]:
        out: list[RepoRef] = []
        page = 1
        while True:
            r = await self._request(
                "GET",
                f"{GITHUB_API}/orgs/{org}/repos",
                params={"per_page": 100, "page": page, "type": "public"},
            )
            data = r.json()
            if not data:
                break
            for repo in data:
                if repo.get("archived") or repo.get("fork"):
                    continue
                out.append(
                    RepoRef(
                        source_id=str(repo["id"]),
                        name=repo["name"],
                        full_name=repo["full_name"],
                        default_branch=repo.get("default_branch") or "main",
                    )
                )
            if len(data) < 100:
                break
            page += 1
        return out

    async def list_merged_prs(
        self, repo: RepoRef, since: datetime
    ) -> list[PRRecord]:
        """Fetch merged PRs in repo updated since `since`, with reviews + first commit."""
        owner, name = repo.full_name.split("/", 1)
        query = """
        query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            pullRequests(
              first: 50
              after: $cursor
              states: MERGED
              orderBy: {field: UPDATED_AT, direction: DESC}
            ) {
              pageInfo { hasNextPage endCursor }
              nodes {
                id databaseId number title url isDraft body
                additions deletions baseRefName
                createdAt mergedAt closedAt updatedAt
                author { login ... on User { databaseId } }
                mergeCommit { messageBody }
                commits(first: 1) {
                  nodes { commit { committedDate authoredDate } }
                }
                reviews(first: 50) {
                  nodes {
                    id databaseId state submittedAt
                    author { login ... on User { databaseId } }
                  }
                }
              }
            }
          }
        }
        """
        out: list[PRRecord] = []
        cursor: str | None = None
        while True:
            r = await self._request(
                "POST",
                GITHUB_GRAPHQL,
                json={"query": query, "variables": {"owner": owner, "name": name, "cursor": cursor}},
            )
            body = r.json()
            if "errors" in body:
                raise RuntimeError(f"GraphQL errors: {body['errors']}")
            page = body["data"]["repository"]["pullRequests"]
            stop = False
            for node in page["nodes"]:
                updated = _parse_dt(node["updatedAt"])
                if updated and updated < since:
                    stop = True
                    continue
                out.append(_to_pr_record(node))
            if stop or not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
        return out

    async def list_deployments(self, repo: RepoRef, since: datetime) -> list[DeploymentRecord]:
        """Tag-based if DEPLOYMENT_TAG_PATTERN is set; else merges to deployment branch."""
        if settings.deployment_tag_pattern:
            return await self._list_tag_deployments(repo, since)
        return await self._list_branch_merge_deployments(repo, since)

    async def _list_branch_merge_deployments(
        self, repo: RepoRef, since: datetime
    ) -> list[DeploymentRecord]:
        owner, name = repo.full_name.split("/", 1)
        branch = settings.deployment_branch or repo.default_branch
        out: list[DeploymentRecord] = []
        page = 1
        while True:
            r = await self._request(
                "GET",
                f"{GITHUB_API}/repos/{owner}/{name}/commits",
                params={
                    "sha": branch,
                    "since": since.isoformat().replace("+00:00", "Z"),
                    "per_page": 100,
                    "page": page,
                },
            )
            data = r.json()
            if not data:
                break
            for commit in data:
                msg = (commit.get("commit") or {}).get("message", "")
                if not msg.lower().startswith("merge"):
                    # Many teams squash-merge; treat all commits on the deploy branch as deployments.
                    pass
                date = _parse_dt((commit["commit"]["committer"] or {}).get("date"))
                if date is None:
                    continue
                out.append(
                    DeploymentRecord(
                        triggered_at=date,
                        signal_type="branch_merge",
                        ref=commit["sha"],
                    )
                )
            if len(data) < 100:
                break
            page += 1
        return out

    async def _list_tag_deployments(
        self, repo: RepoRef, since: datetime
    ) -> list[DeploymentRecord]:
        import fnmatch

        owner, name = repo.full_name.split("/", 1)
        pattern = settings.deployment_tag_pattern or "v*"
        out: list[DeploymentRecord] = []
        page = 1
        while True:
            r = await self._request(
                "GET",
                f"{GITHUB_API}/repos/{owner}/{name}/tags",
                params={"per_page": 100, "page": page},
            )
            data = r.json()
            if not data:
                break
            for tag in data:
                if not fnmatch.fnmatch(tag["name"], pattern):
                    continue
                # Tag → commit → date
                sha = tag["commit"]["sha"]
                cr = await self._request(
                    "GET", f"{GITHUB_API}/repos/{owner}/{name}/commits/{sha}"
                )
                cdata = cr.json()
                date = _parse_dt((cdata["commit"]["committer"] or {}).get("date"))
                if date is None or date < since:
                    continue
                out.append(
                    DeploymentRecord(triggered_at=date, signal_type="tag", ref=tag["name"])
                )
            if len(data) < 100:
                break
            page += 1
        return out


def _to_pr_record(node: dict[str, Any]) -> PRRecord:
    author = node.get("author") or {}
    commits_nodes = (node.get("commits") or {}).get("nodes") or []
    first_commit_at = None
    if commits_nodes:
        c = commits_nodes[0]["commit"]
        first_commit_at = _parse_dt(c.get("authoredDate") or c.get("committedDate"))

    reviews: list[ReviewRecord] = []
    for rv in (node.get("reviews") or {}).get("nodes", []) or []:
        rva = rv.get("author") or {}
        sub = _parse_dt(rv.get("submittedAt"))
        if sub is None:
            continue
        reviews.append(
            ReviewRecord(
                source_id=str(rv.get("databaseId") or rv.get("id")),
                reviewer_login=rva.get("login"),
                reviewer_source_id=str(rva["databaseId"]) if rva.get("databaseId") else None,
                submitted_at=sub,
                state=rv.get("state", "COMMENTED"),
            )
        )

    merge_commit = node.get("mergeCommit") or {}
    return PRRecord(
        source_id=str(node.get("databaseId") or node.get("id")),
        number=int(node["number"]),
        title=node.get("title", "") or "",
        url=node.get("url", "") or "",
        author_login=author.get("login"),
        author_source_id=str(author["databaseId"]) if author.get("databaseId") else None,
        opened_at=_parse_dt(node["createdAt"]) or datetime.now(timezone.utc),
        merged_at=_parse_dt(node.get("mergedAt")),
        closed_at=_parse_dt(node.get("closedAt")),
        additions=int(node.get("additions") or 0),
        deletions=int(node.get("deletions") or 0),
        base_branch=node.get("baseRefName") or "main",
        is_draft=bool(node.get("isDraft")),
        first_commit_at=first_commit_at,
        reviews=reviews,
        body=node.get("body"),
        merge_commit_body=merge_commit.get("messageBody"),
    )


def backfill_since() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=30 * settings.backfill_months)
