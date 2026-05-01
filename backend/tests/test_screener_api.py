"""Tests for screener API — auth + endpoint contracts (Firestore + LLM mocked)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app


# ── /run requires X-Scheduler-Token ─────────────────────────────────────────


@patch("api.routes.screener.settings")
def test_run_endpoint_rejects_missing_token(mock_settings):
    mock_settings.screener_runner_token = "secret-abc"
    with TestClient(app) as client:
        resp = client.post(
            "/api/screener/run", json={"profile": "momentum", "frequency": "weekly"}
        )
    assert resp.status_code == 401


@patch("api.routes.screener.settings")
def test_run_endpoint_returns_503_when_unconfigured(mock_settings):
    mock_settings.screener_runner_token = ""
    with TestClient(app) as client:
        resp = client.post(
            "/api/screener/run",
            json={"profile": "momentum", "frequency": "weekly"},
            headers={"X-Scheduler-Token": "anything"},
        )
    assert resp.status_code == 503


# ── /unsubscribe (no auth required) ─────────────────────────────────────────


@patch("api.routes.screener.disable_subscriber", return_value=True)
@patch("api.routes.screener.verify_unsubscribe_token", return_value="user-1")
def test_unsubscribe_valid_token(mock_verify, mock_disable):
    with TestClient(app) as client:
        resp = client.get("/api/screener/unsubscribe?token=valid")
    assert resp.status_code == 200
    assert "已取消訂閱" in resp.text
    mock_disable.assert_called_once_with("user-1")


@patch("api.routes.screener.verify_unsubscribe_token", return_value=None)
def test_unsubscribe_invalid_token_returns_400(_):
    with TestClient(app) as client:
        resp = client.get("/api/screener/unsubscribe?token=bad")
    assert resp.status_code == 400


# ── /reports — Firestore mocked ─────────────────────────────────────────────


@pytest.fixture
def fake_db():
    db = MagicMock()
    snap1 = MagicMock()
    snap1.to_dict.return_value = {
        "report_id": "20260501-weekly-momentum",
        "profile": "momentum",
        "frequency": "weekly",
        "final_count": 5,
        "industries_covered": ["半導體"],
        "duration_seconds": 100,
        "status": "completed",
    }
    snap2 = MagicMock()
    snap2.to_dict.return_value = {
        "report_id": "20260424-weekly-value",
        "profile": "value",
        "frequency": "weekly",
        "final_count": 4,
        "industries_covered": ["金融保險"],
        "duration_seconds": 80,
        "status": "completed",
    }
    db.collection.return_value.stream.return_value = [snap1, snap2]
    return db


@patch("api.routes.screener.get_db")
def test_list_reports_filters_by_profile(mock_get_db, fake_db):
    mock_get_db.return_value = fake_db
    # 用 dependency_overrides 完全跳過 Firebase auth
    from api.routes.screener import verify_firebase_token  # 路由實際使用的同一個 obj

    app.dependency_overrides[verify_firebase_token] = lambda: {"uid": "u", "email": "e"}
    try:
        with TestClient(app) as client:
            resp = client.get("/api/screener/reports?profile=momentum")
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["profile"] == "momentum" for r in data)
    finally:
        app.dependency_overrides.clear()
