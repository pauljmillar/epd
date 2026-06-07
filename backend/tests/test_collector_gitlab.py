from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.collectors.gitlab import GITLAB_API, GitLabClient, RepoRef, _notes_to_reviews


@pytest.mark.asyncio
@respx.mock
async def test_list_group_projects_includes_subgroups_excludes_archived():
    # Service returns the data filtered as we requested; the request URL must include
    # include_subgroups=true and archived=false.
    route = respx.get(f"{GITLAB_API}/groups/myorg/projects").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "name": "alpha",
                    "path_with_namespace": "myorg/alpha",
                    "default_branch": "main",
                },
                {
                    "id": 2,
                    "name": "beta",
                    "path_with_namespace": "myorg/sub/beta",
                    "default_branch": "trunk",
                },
            ],
        )
    )
    async with GitLabClient("tok") as gl:
        repos = await gl.list_group_projects("myorg")
    assert [r.full_name for r in repos] == ["myorg/alpha", "myorg/sub/beta"]
    assert repos[1].default_branch == "trunk"
    # Confirm the request actually asked for subgroups + non-archived.
    call = route.calls[0]
    assert "include_subgroups=true" in str(call.request.url)
    assert "archived=false" in str(call.request.url)


@pytest.mark.asyncio
@respx.mock
async def test_list_merged_mrs_pulls_detail_commits_notes():
    list_url = f"{GITLAB_API}/projects/42/merge_requests"
    detail_url = f"{GITLAB_API}/projects/42/merge_requests/7"
    commits_url = f"{GITLAB_API}/projects/42/merge_requests/7/commits"
    notes_url = f"{GITLAB_API}/projects/42/merge_requests/7/notes"

    respx.get(list_url).mock(
        return_value=httpx.Response(
            200,
            json=[{"iid": 7, "title": "Fix thing"}],
            headers={"X-Next-Page": ""},
        )
    )
    respx.get(detail_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 901,
                "iid": 7,
                "title": "Fix thing",
                "web_url": "https://gitlab.com/myorg/alpha/-/merge_requests/7",
                "description": "Generated with [Claude Code]",
                "author": {"id": 11, "username": "alice"},
                "created_at": "2026-06-01T10:00:00Z",
                "merged_at": "2026-06-02T10:00:00Z",
                "closed_at": "2026-06-02T10:00:00Z",
                "target_branch": "main",
                "draft": False,
                "additions": 20,
                "deletions": 5,
            },
        )
    )
    respx.get(commits_url).mock(
        return_value=httpx.Response(
            200,
            json=[
                # GitLab returns reverse-chronological; we take the oldest.
                {"id": "c2", "authored_date": "2026-06-01T09:00:00Z"},
                {"id": "c1", "authored_date": "2026-05-30T08:00:00Z"},
            ],
            headers={"X-Next-Page": ""},
        )
    )
    respx.get(notes_url).mock(
        return_value=httpx.Response(
            200,
            json=[
                # system note — ignored
                {"id": 1, "system": True, "author": {"username": "ghost"}},
                # author's own note — ignored
                {
                    "id": 2,
                    "system": False,
                    "author": {"id": 11, "username": "alice"},
                    "created_at": "2026-06-01T11:00:00Z",
                    "body": "self-comment",
                },
                # real review
                {
                    "id": 3,
                    "system": False,
                    "author": {"id": 22, "username": "bob"},
                    "created_at": "2026-06-01T15:00:00Z",
                    "body": "lgtm",
                },
            ],
            headers={"X-Next-Page": ""},
        )
    )

    async with GitLabClient("tok") as gl:
        mrs = await gl.list_merged_mrs(
            RepoRef("42", "alpha", "myorg/alpha", "main"),
            since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    assert len(mrs) == 1
    mr = mrs[0]
    assert mr.number == 7
    assert mr.author_login == "alice"
    assert mr.additions == 20 and mr.deletions == 5
    assert mr.first_commit_at == datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
    assert len(mr.reviews) == 1
    assert mr.reviews[0].reviewer_login == "bob"
    assert mr.reviews[0].state == "APPROVED"  # "lgtm" → approval
    assert mr.body and "Claude Code" in mr.body


def test_notes_to_reviews_filters_correctly():
    notes = [
        {"system": True, "author": {"username": "x"}, "created_at": "2026-06-01T00:00:00Z"},
        {
            "system": False,
            "author": {"username": "alice"},
            "created_at": "2026-06-01T01:00:00Z",
            "body": "thanks",
        },
        {
            "system": False,
            "author": {"username": "bob", "id": 22},
            "created_at": "2026-06-01T02:00:00Z",
            "body": "looks good",
            "id": 99,
        },
    ]
    out = _notes_to_reviews(notes, "alice")
    assert len(out) == 1
    assert out[0].reviewer_login == "bob"
    assert out[0].state == "COMMENTED"
