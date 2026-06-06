from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.collectors.github import GITHUB_API, GITHUB_GRAPHQL, GitHubClient, RepoRef


@pytest.mark.asyncio
@respx.mock
async def test_list_org_repos_paginates_and_filters_forks_and_archived():
    page1 = [
        {"id": 1, "name": "good", "full_name": "o/good", "default_branch": "main",
         "archived": False, "fork": False},
        {"id": 2, "name": "fork", "full_name": "o/fork", "default_branch": "main",
         "archived": False, "fork": True},
        {"id": 3, "name": "old", "full_name": "o/old", "default_branch": "main",
         "archived": True, "fork": False},
    ]
    respx.get(f"{GITHUB_API}/orgs/o/repos").mock(return_value=httpx.Response(200, json=page1))

    async with GitHubClient("tok") as gh:
        repos = await gh.list_org_repos("o")
    assert len(repos) == 1
    assert repos[0].full_name == "o/good"


@pytest.mark.asyncio
@respx.mock
async def test_list_merged_prs_extracts_first_commit_and_reviews():
    body = {
        "data": {
            "repository": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "id": "PR_1",
                            "databaseId": 1,
                            "number": 42,
                            "title": "Fix bug",
                            "url": "https://github.com/o/good/pull/42",
                            "isDraft": False,
                            "body": "Closes #100\n\n🤖 Generated with [Claude Code]",
                            "additions": 10,
                            "deletions": 3,
                            "baseRefName": "main",
                            "createdAt": "2026-06-01T10:00:00Z",
                            "mergedAt": "2026-06-02T10:00:00Z",
                            "closedAt": "2026-06-02T10:00:00Z",
                            "updatedAt": "2026-06-02T10:00:00Z",
                            "author": {"login": "alice", "databaseId": 100},
                            "mergeCommit": {
                                "messageBody": "Co-Authored-By: Claude <noreply@anthropic.com>"
                            },
                            "commits": {
                                "nodes": [
                                    {"commit": {
                                        "authoredDate": "2026-05-30T08:00:00Z",
                                        "committedDate": "2026-05-30T08:00:00Z"}}
                                ]
                            },
                            "reviews": {
                                "nodes": [
                                    {"id": "R_1", "databaseId": 11, "state": "APPROVED",
                                     "submittedAt": "2026-06-01T15:00:00Z",
                                     "author": {"login": "bob", "databaseId": 200}}
                                ]
                            },
                        }
                    ],
                }
            }
        }
    }
    respx.post(GITHUB_GRAPHQL).mock(return_value=httpx.Response(200, json=body))

    async with GitHubClient("tok") as gh:
        prs = await gh.list_merged_prs(
            RepoRef("1", "good", "o/good", "main"),
            since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    assert len(prs) == 1
    pr = prs[0]
    assert pr.number == 42
    assert pr.author_login == "alice"
    assert pr.first_commit_at == datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
    assert len(pr.reviews) == 1
    assert pr.reviews[0].reviewer_login == "bob"
    assert pr.reviews[0].state == "APPROVED"
    assert pr.body and "Claude Code" in pr.body
    assert pr.merge_commit_body and "Anthropic" in pr.merge_commit_body or "anthropic" in pr.merge_commit_body
