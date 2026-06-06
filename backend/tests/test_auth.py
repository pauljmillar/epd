from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_health_always_public(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "secret")
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["auth_required"] is True


def test_metrics_open_when_no_password(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", None)
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.json()["auth_required"] is False


def test_metrics_rejects_without_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "secret")
    client = TestClient(app)
    r = client.get("/api/v1/metrics/org")
    assert r.status_code == 401


def test_metrics_accepts_correct_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "secret")
    client = TestClient(app)
    # This will 500 because there's no DB in tests, but we want to confirm we got past auth.
    r = client.get(
        "/api/v1/metrics/org",
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code != 401


def test_auth_check_passes_with_valid_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "secret")
    client = TestClient(app)
    r = client.post(
        "/api/v1/auth/check", headers={"Authorization": "Bearer secret"}
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_auth_check_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "secret")
    client = TestClient(app)
    r = client.post(
        "/api/v1/auth/check", headers={"Authorization": "Bearer wrong"}
    )
    assert r.status_code == 401
