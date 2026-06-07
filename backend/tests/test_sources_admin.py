"""Tests for the data_sources admin endpoints. Uses the same real Supabase DB the other
tests do (we run alembic ahead of time)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.config import settings
from app.db import session_scope
from app.main import app
from app.models import DataSource


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    """All admin routes go through require_auth — disable for tests so we don't have to
    set ADMIN_PASSWORD just to call them."""
    monkeypatch.setattr(settings, "admin_password", None)


@pytest.fixture
def clean_sources():
    """Wipe all data_sources rows around each test so the unique constraint doesn't bite."""
    with session_scope() as s:
        s.execute(delete(DataSource))
    yield
    with session_scope() as s:
        s.execute(delete(DataSource))


def test_create_list_patch_softremove(clean_sources):
    client = TestClient(app)

    # Create
    r = client.post(
        "/api/v1/admin/sources",
        json={"source": "github", "org_or_group": "testorg", "token": "ghp_TESTTOKEN"},
    )
    assert r.status_code == 201, r.text
    src = r.json()
    src_id = src["id"]
    assert src["source"] == "github"
    assert src["org_or_group"] == "testorg"
    assert src["is_active"] is True
    assert "token" not in src
    assert "ghp_…OKEN" == src["token_preview"]

    # Duplicate rejected
    r2 = client.post(
        "/api/v1/admin/sources",
        json={"source": "github", "org_or_group": "testorg", "token": "x"},
    )
    assert r2.status_code == 409

    # List
    r3 = client.get("/api/v1/admin/sources")
    assert r3.status_code == 200
    assert any(s["id"] == src_id for s in r3.json()["sources"])

    # Patch — toggle is_active off, then back on
    r4 = client.patch(f"/api/v1/admin/sources/{src_id}", json={"is_active": False})
    assert r4.status_code == 200
    assert r4.json()["is_active"] is False

    r5 = client.patch(f"/api/v1/admin/sources/{src_id}", json={"is_active": True, "token": "new_token"})
    assert r5.status_code == 200
    assert r5.json()["is_active"] is True
    assert "new_…oken" == r5.json()["token_preview"]

    # Soft remove
    r6 = client.delete(f"/api/v1/admin/sources/{src_id}")
    assert r6.status_code == 200
    assert r6.json()["soft_removed"] is True

    # Soft-removed source is still listed but marked inactive
    listed = next(
        s for s in client.get("/api/v1/admin/sources").json()["sources"] if s["id"] == src_id
    )
    assert listed["is_active"] is False


def test_purge_removes_source_row(clean_sources):
    client = TestClient(app)
    r = client.post(
        "/api/v1/admin/sources",
        json={"source": "gitlab", "org_or_group": "g/sub", "token": "glpat_x"},
    )
    src_id = r.json()["id"]

    pr = client.post(f"/api/v1/admin/sources/{src_id}/purge")
    assert pr.status_code == 200
    body = pr.json()
    assert body["purged"] is True
    assert body["deleted_repos"] == 0  # no repos linked in this fresh test

    # Source row should be gone
    rows = client.get("/api/v1/admin/sources").json()["sources"]
    assert not any(s["id"] == src_id for s in rows)


def test_validation_rejects_unknown_source(clean_sources):
    client = TestClient(app)
    r = client.post(
        "/api/v1/admin/sources",
        json={"source": "bitbucket", "org_or_group": "x", "token": "y"},
    )
    assert r.status_code == 422


def test_seed_from_env_vars_is_idempotent(clean_sources, monkeypatch):
    from app.sources import seed_from_env_vars

    monkeypatch.setattr(settings, "github_token", "ghp_env_seed")
    monkeypatch.setattr(settings, "github_org", "seeded_org")
    monkeypatch.setattr(settings, "gitlab_token", None)
    monkeypatch.setattr(settings, "gitlab_group", None)

    assert seed_from_env_vars() == 1  # first call creates
    assert seed_from_env_vars() == 0  # second call is a no-op

    # Confirm row exists
    with session_scope() as s:
        from sqlalchemy import select
        row = s.execute(
            select(DataSource).where(DataSource.source == "github", DataSource.org_or_group == "seeded_org")
        ).scalar_one()
        assert row.token == "ghp_env_seed"
