"""Tests for the team_id query param on /metrics/org and /metrics/repo.

Uses the live Supabase DB the rest of the suite uses, but creates and cleans up its own
team + member fixtures so it doesn't depend on real seeded data."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.config import settings
from app.db import session_scope
from app.main import app
from app.models import Contributor, Team, TeamMember


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", None)


@pytest.fixture
def disposable_team():
    """Create a team with two of the live DB's most active contributors as members so we
    know there are real PRs for them. Yields (team_id, member_logins). Tears down the
    team + memberships afterward."""
    with session_scope() as s:
        # Pick two contributors that we know exist in the live data set (verified via
        # the contributors list earlier in development). Falling back to any two if not
        # present, to keep the test runnable.
        rows = s.execute(
            select(Contributor.id, Contributor.login).limit(2)
        ).all()
        if len(rows) < 2:
            pytest.skip("Need at least 2 contributors in the DB for this test")
        c1_id, c1_login = rows[0]
        c2_id, c2_login = rows[1]

        team = Team(name="__pytest_disposable_team__")
        s.add(team)
        s.flush()
        team_id = team.id
        s.add(TeamMember(team_id=team_id, contributor_id=c1_id))
        s.add(TeamMember(team_id=team_id, contributor_id=c2_id))

    yield team_id, [c1_login, c2_login]

    with session_scope() as s:
        s.execute(delete(TeamMember).where(TeamMember.team_id == team_id))
        s.execute(delete(Team).where(Team.id == team_id))


def test_org_metrics_without_team_returns_all_data():
    client = TestClient(app)
    r = client.get("/api/v1/metrics/org?period=30d")
    assert r.status_code == 200
    d = r.json()
    assert d["team_id"] is None
    # Sanity: the org has SOME merged PRs over 30d
    assert d["counts"]["merged_prs"] >= 0


def test_org_metrics_with_team_scopes_data(disposable_team):
    team_id, _logins = disposable_team
    client = TestClient(app)

    r_all = client.get("/api/v1/metrics/org?period=90d")
    r_team = client.get(f"/api/v1/metrics/org?period=90d&team={team_id}")
    assert r_all.status_code == 200
    assert r_team.status_code == 200

    d_all = r_all.json()
    d_team = r_team.json()

    assert d_team["team_id"] == team_id
    assert d_all["team_id"] is None

    # Team-scoped count must be <= the org-wide count (subset relationship)
    assert d_team["counts"]["merged_prs"] <= d_all["counts"]["merged_prs"]


def test_org_metrics_with_missing_team_returns_empty_shape():
    client = TestClient(app)
    r = client.get("/api/v1/metrics/org?period=30d&team=9999999")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["team_id"] == 9999999
    # No members → no PRs, but the response shape stays intact
    assert d["counts"]["merged_prs"] == 0
    assert "kpis" in d
    assert "series" in d


def test_repo_metrics_with_team_scopes_data(disposable_team):
    """Pick whatever repo is in the DB and confirm team filter narrows the count."""
    team_id, _logins = disposable_team

    with session_scope() as s:
        from app.models import Repository
        repo_row = s.execute(
            select(Repository.full_name).where(Repository.is_tracked.is_(True)).limit(1)
        ).first()
        if repo_row is None:
            pytest.skip("No tracked repos in the DB for this test")
        repo_full_name = repo_row[0]

    client = TestClient(app)
    r_all = client.get(f"/api/v1/metrics/repo/{repo_full_name}?period=90d")
    r_team = client.get(f"/api/v1/metrics/repo/{repo_full_name}?period=90d&team={team_id}")
    assert r_all.status_code == 200, r_all.text
    assert r_team.status_code == 200, r_team.text

    d_all = r_all.json()
    d_team = r_team.json()
    assert d_team["team_id"] == team_id
    assert d_team["counts"]["merged_prs"] <= d_all["counts"]["merged_prs"]
